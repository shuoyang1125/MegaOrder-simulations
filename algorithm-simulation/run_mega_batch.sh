#!/usr/bin/env bash

# Run five Mega experiments serially. A task may be terminated only after its
# two expected mega.csv rows and all six pickle artifacts are safely persisted.
set -u

PROJECT_DIR="/home/zyxl/MegaTE-main"
WORK_DIR="${PROJECT_DIR}/benchmarks"
CSV_PATH="${WORK_DIR}/mega.csv"
LOG_DIR="${MEGA_BATCH_LOG_DIR:-${PROJECT_DIR}/experiment_logs/mega_uscarrier_server100_csv_watch}"
PYTHON_BIN="/home/zyxl/miniconda3/envs/megate/bin/python"
POLL_SECONDS=5
TERM_GRACE_SECONDS=120

slice_a=(10 12 14 16 18)
slice_b=(11 13 15 17 19)
seed_a=(11000 13000 15000 17000 19000)
seed_b=(12000 14000 16000 18000 20000)

mkdir -p "${LOG_DIR}"
cd "${WORK_DIR}" || exit 1

printf 'batch_started=%s\nwork_dir=%s\nlog_dir=%s\npython=%s\n' \
    "$(date --iso-8601=seconds)" "${WORK_DIR}" "${LOG_DIR}" "${PYTHON_BIN}" \
    > "${LOG_DIR}/batch.info"

process_is_live() {
    local pid="$1"
    local state
    kill -0 "${pid}" 2>/dev/null || return 1
    state="$(awk '{print $3}' "/proc/${pid}/stat" 2>/dev/null)"
    [[ -n "${state}" && "${state}" != "Z" ]]
}

group_has_live_processes() {
    local sid="$1"
    ps -eo sid=,stat= | awk -v sid="${sid}" \
        '$1 == sid && $2 !~ /^Z/ {found=1} END {exit !found}'
}

file_signature() {
    local path="$1"
    stat -c '%i:%s:%y' "${path}" 2>/dev/null || printf 'MISSING\n'
}

result_handles_closed() {
    local pid="$1"
    local first_dir="$2"
    local second_dir="$3"
    local fd target

    [[ -d "/proc/${pid}/fd" ]] || return 0
    for fd in "/proc/${pid}/fd/"*; do
        target="$(readlink "${fd}" 2>/dev/null)" || continue
        case "${target}" in
            "${CSV_PATH}"|"${first_dir}/"*|"${second_dir}/"*) return 1 ;;
        esac
    done
    return 0
}

validate_csv_append() {
    local start_line="$1"
    local expected_seed_a="$2"
    local expected_seed_b="$3"

    awk -F',' -v start="${start_line}" \
        -v seed_a="${expected_seed_a}" -v seed_b="${expected_seed_b}" '
        NR <= start { next }
        { count++; field_count[count] = NF; row[count] = $0 }
        END {
            if (count != 3) exit 1
            split(row[1], header, ",")
            if (field_count[1] != 24 || header[1] != "problem" ||
                header[4] != "traffic_seed" || header[9] != "algo" ||
                header[13] != "server_per_site") exit 2
            split(row[2], first, ",")
            if (field_count[2] != 24 || first[1] != "UsCarrier.graphml" ||
                first[4] + 0 != seed_a || first[6] != "generic" ||
                first[9] != "mega" || first[13] != "100" ||
                first[22] + 0 != 0.1 || first[23] + 0 != 1.0) exit 3
            split(row[3], second, ",")
            if (field_count[3] != 24 || second[1] != "UsCarrier.graphml" ||
                second[4] + 0 != seed_b || second[6] != "generic" ||
                second[9] != "mega" || second[13] != "100" ||
                second[22] + 0 != 0.1 || second[23] + 0 != 1.0) exit 4
        }
    ' "${CSV_PATH}"
}

artifacts_are_fresh() {
    local -n paths_ref="$1"
    local -n signatures_ref="$2"
    local idx current

    for idx in 0 1 2 3 4 5; do
        [[ -s "${paths_ref[idx]}" ]] || return 1
        current="$(file_signature "${paths_ref[idx]}")"
        [[ "${current}" != "${signatures_ref[idx]}" ]] || return 1
    done
    return 0
}

sync_artifacts() {
    local -n paths_ref="$1"
    local path
    for path in "${paths_ref[@]}"; do
        sync -f "${path}" || return 1
    done
    sync -f "${CSV_PATH}"
}

wait_for_group_exit() {
    local sid="$1"
    local info_file="$2"
    local elapsed=0

    while group_has_live_processes "${sid}"; do
        if (( elapsed >= TERM_GRACE_SECONDS )); then
            printf 'sigkill_sent=%s\n' "$(date --iso-8601=seconds)" \
                >> "${info_file}"
            kill -KILL -- "-${sid}" 2>/dev/null || true
            break
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    while group_has_live_processes "${sid}"; do
        sleep 1
    done
}

for index in 0 1 2 3 4; do
    task_no=$((index + 1))
    first_slice="${slice_a[index]}"
    second_slice="${slice_b[index]}"
    first_seed="${seed_a[index]}"
    second_seed="${seed_b[index]}"
    task_name="mega_slices_${first_slice}_${second_slice}"
    stdout_log="${LOG_DIR}/${task_name}.stdout.log"
    stderr_log="${LOG_DIR}/${task_name}.stderr.log"
    info_file="${LOG_DIR}/${task_name}.info"
    status_file="${LOG_DIR}/${task_name}.exit_status"

    first_dir="${WORK_DIR}/Mega-logs/UsCarrier.graphml/${first_seed}-generic/100-per_site"
    second_dir="${WORK_DIR}/Mega-logs/UsCarrier.graphml/${second_seed}-generic/100-per_site"
    lp_sol_name="UsCarrier.graphml-LP-in-mega_4-paths_edge-disjoint-False_dist-metric-inv-cap_sol-dict.pkl"
    lp_input_name="UsCarrier.graphml-100-LP-in-mega_ssp_input.pkl"
    ssp_name="UsCarrier.graphml-100-ssp_solution.pkl"
    artifact_paths=(
        "${first_dir}/${lp_sol_name}"
        "${first_dir}/${lp_input_name}"
        "${first_dir}/${ssp_name}"
        "${second_dir}/${lp_sol_name}"
        "${second_dir}/${lp_input_name}"
        "${second_dir}/${ssp_name}"
    )
    artifact_before=()
    for path in "${artifact_paths[@]}"; do
        artifact_before+=("$(file_signature "${path}")")
    done

    touch "${CSV_PATH}"
    start_line="$(wc -l < "${CSV_PATH}")"
    start_size="$(stat -c '%s' "${CSV_PATH}")"
    start_inode="$(stat -c '%i' "${CSV_PATH}")"
    start_epoch="$(date +%s)"
    start_iso="$(date --iso-8601=seconds)"

    printf 'task=%s\nstarted=%s\nslices=%s %s\nexpected_seeds=%s %s\ncsv_start_line=%s\ncsv_start_size=%s\ncsv_inode=%s\ncommand=%s\n' \
        "${task_name}" "${start_iso}" "${first_slice}" "${second_slice}" \
        "${first_seed}" "${second_seed}" "${start_line}" "${start_size}" \
        "${start_inode}" \
        "python Run_all.py --algo mega --server 100 --problem UsCarrier.graphml --slices ${first_slice} ${second_slice} --epsilon 0.1 --lambda 1" \
        > "${info_file}"

    printf '[%s] Starting task %d/5 (slices %s %s; seeds %s %s)\n' \
        "${start_iso}" "${task_no}" "${first_slice}" "${second_slice}" \
        "${first_seed}" "${second_seed}"

    setsid "${PYTHON_BIN}" Run_all.py \
        --algo mega \
        --server 100 \
        --problem UsCarrier.graphml \
        --slices "${first_slice}" "${second_slice}" \
        --epsilon 0.1 \
        --lambda 1 \
        > "${stdout_log}" 2> "${stderr_log}" &
    task_pid=$!
    task_sid="${task_pid}"
    printf 'pid=%s\nsid=%s\n' "${task_pid}" "${task_sid}" >> "${info_file}"

    results_confirmed=0
    termination_requested=0
    validation_failure=0

    while process_is_live "${task_pid}"; do
        current_inode="$(stat -c '%i' "${CSV_PATH}" 2>/dev/null)"
        if [[ "${current_inode}" != "${start_inode}" ]]; then
            printf 'validation_error=mega.csv inode changed during task\n' \
                >> "${info_file}"
            validation_failure=1
            break
        fi

        current_line="$(wc -l < "${CSV_PATH}")"
        new_lines=$((current_line - start_line))
        if (( new_lines > 3 )); then
            printf 'validation_error=more than three CSV lines were appended\n' \
                >> "${info_file}"
            validation_failure=1
            break
        fi

        if (( new_lines == 3 )) && \
           validate_csv_append "${start_line}" "${first_seed}" "${second_seed}" && \
           artifacts_are_fresh artifact_paths artifact_before && \
           result_handles_closed "${task_pid}" "${first_dir}" "${second_dir}"; then
            if ! sync_artifacts artifact_paths; then
                printf 'validation_error=sync failed\n' >> "${info_file}"
                validation_failure=1
                break
            fi
            results_confirmed=1
            csv_complete_time="$(date --iso-8601=seconds)"
            printf 'csv_complete=%s\ncsv_end_line=%s\ncsv_end_size=%s\nresults_synced=%s\n' \
                "${csv_complete_time}" "${current_line}" \
                "$(stat -c '%s' "${CSV_PATH}")" \
                "$(date --iso-8601=seconds)" >> "${info_file}"

            if process_is_live "${task_pid}"; then
                termination_requested=1
                printf 'sigterm_sent=%s\n' "$(date --iso-8601=seconds)" \
                    >> "${info_file}"
                kill -TERM -- "-${task_sid}" 2>/dev/null || \
                    kill -TERM "${task_pid}" 2>/dev/null || true
            fi
            break
        fi

        sleep "${POLL_SECONDS}"
    done

    if (( termination_requested )); then
        wait_for_group_exit "${task_sid}" "${info_file}"
    fi

    wait "${task_pid}"
    rc=$?

    if (( ! results_confirmed )); then
        current_line="$(wc -l < "${CSV_PATH}")"
        if [[ "$(stat -c '%i' "${CSV_PATH}")" == "${start_inode}" ]] && \
           (( current_line - start_line == 3 )) && \
           validate_csv_append "${start_line}" "${first_seed}" "${second_seed}" && \
           artifacts_are_fresh artifact_paths artifact_before && \
           sync_artifacts artifact_paths; then
            results_confirmed=1
            printf 'csv_complete=%s\ncsv_end_line=%s\ncsv_end_size=%s\nresults_synced=%s\n' \
                "$(date --iso-8601=seconds)" "${current_line}" \
                "$(stat -c '%s' "${CSV_PATH}")" \
                "$(date --iso-8601=seconds)" >> "${info_file}"
        fi
    fi

    end_epoch="$(date +%s)"
    duration_seconds=$((end_epoch - start_epoch))
    printf '%s\n' "${rc}" > "${status_file}"
    printf 'process_exited=%s\nduration_seconds=%s\nexit_status=%s\ntermination_requested=%s\n' \
        "$(date --iso-8601=seconds)" "${duration_seconds}" "${rc}" \
        "${termination_requested}" >> "${info_file}"

    if (( ! results_confirmed || validation_failure )); then
        cp "${info_file}" "${LOG_DIR}/failed_command.info"
        printf 'batch_finished=%s\nexit_status=%s\nfailed_task=%s\nreason=result validation failed\n' \
            "$(date --iso-8601=seconds)" "${rc}" "${task_name}" \
            >> "${LOG_DIR}/batch.info"
        printf '[%s] Task %d/5 did not produce validated complete results; stopping.\n' \
            "$(date --iso-8601=seconds)" "${task_no}" >&2
        exit 1
    fi

    if (( ! termination_requested && rc != 0 )); then
        cp "${info_file}" "${LOG_DIR}/failed_command.info"
        printf 'batch_finished=%s\nexit_status=%s\nfailed_task=%s\nreason=process exited abnormally\n' \
            "$(date --iso-8601=seconds)" "${rc}" "${task_name}" \
            >> "${LOG_DIR}/batch.info"
        printf '[%s] Task %d/5 exited abnormally with status %s; stopping.\n' \
            "$(date --iso-8601=seconds)" "${task_no}" "${rc}" >&2
        exit "${rc}"
    fi

    printf '[%s] Task %d/5 results persisted; process exited with status %s.\n' \
        "$(date --iso-8601=seconds)" "${task_no}" "${rc}"
done

printf 'batch_finished=%s\nexit_status=0\n' "$(date --iso-8601=seconds)" \
    >> "${LOG_DIR}/batch.info"
printf '[%s] All 5 Mega tasks completed successfully.\n' \
    "$(date --iso-8601=seconds)"
