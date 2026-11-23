#!/usr/bin/env bash

# Run TSE experiments serially. A task may be terminated only after its two
# expected CSV rows are validated, the CSV handle is closed, and CSV is synced.
set -u

PROJECT_DIR="/home/zyxl/MegaTE-main"
WORK_DIR="${PROJECT_DIR}/benchmarks"
CSV_PATH="${WORK_DIR}/tse.csv"
LOG_DIR="${TSE_BATCH_LOG_DIR:-${PROJECT_DIR}/experiment_logs/tse_uscarrier_server100_csv_watch}"
PYTHON_BIN="/home/zyxl/miniconda3/envs/megate/bin/python"
START_TASK="${TSE_START_TASK:-1}"
POLL_SECONDS=5
TERM_GRACE_SECONDS=60

slice_a=(2 4 6 8 10 12 14 16 18)
slice_b=(3 5 7 9 11 13 15 17 19)
seed_a=(3000 5000 7000 9000 11000 13000 15000 17000 19000)
seed_b=(4000 6000 8000 10000 12000 14000 16000 18000 20000)

mkdir -p "${LOG_DIR}"
cd "${WORK_DIR}" || exit 1

if (( START_TASK < 1 || START_TASK > 9 )); then
    printf 'TSE_START_TASK must be between 1 and 9\n' >&2
    exit 2
fi

printf 'batch_started=%s\nwork_dir=%s\nlog_dir=%s\npython=%s\nstart_task=%s\n' \
    "$(date --iso-8601=seconds)" "${WORK_DIR}" "${LOG_DIR}" \
    "${PYTHON_BIN}" "${START_TASK}" > "${LOG_DIR}/batch.info"

process_is_live() {
    local pid="$1"
    local state
    kill -0 "${pid}" 2>/dev/null || return 1
    state="$(awk '{print $3}' "/proc/${pid}/stat" 2>/dev/null)"
    [[ "${state}" != "Z" && -n "${state}" ]]
}

group_has_live_processes() {
    local sid="$1"
    ps -eo sid=,stat= | awk -v sid="${sid}" \
        '$1 == sid && $2 !~ /^Z/ {found=1} END {exit !found}'
}

csv_handle_closed() {
    local pid="$1"
    local fd target

    [[ -d "/proc/${pid}/fd" ]] || return 0
    for fd in "/proc/${pid}/fd/"*; do
        target="$(readlink "${fd}" 2>/dev/null)" || continue
        if [[ "${target}" == "${CSV_PATH}" ]]; then
            return 1
        fi
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
            if (field_count[1] != 23 || header[1] != "problem" ||
                header[2] != "tm_index" || header[3] != "traffic_seed") exit 2
            split(row[2], first, ",")
            if (field_count[2] != 23 || first[1] != "UsCarrier.graphml" ||
                first[2] != "0" || first[3] + 0 != seed_a ||
                first[4] != "100" || first[5] != "tse" ||
                first[6] + 0 != 0.1 || first[7] + 0 != 1.0) exit 3
            split(row[3], second, ",")
            if (field_count[3] != 23 || second[1] != "UsCarrier.graphml" ||
                second[2] != "1" || second[3] + 0 != seed_b ||
                second[4] != "100" || second[5] != "tse" ||
                second[6] + 0 != 0.1 || second[7] + 0 != 1.0) exit 4
        }
    ' "${CSV_PATH}"
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

for index in 0 1 2 3 4 5 6 7 8; do
    task_no=$((index + 1))
    (( task_no < START_TASK )) && continue

    first_slice="${slice_a[index]}"
    second_slice="${slice_b[index]}"
    first_seed="${seed_a[index]}"
    second_seed="${seed_b[index]}"
    task_name="task$(printf '%02d' "${task_no}")_s${first_slice}_${second_slice}"
    stdout_log="${LOG_DIR}/${task_name}.stdout.log"
    stderr_log="${LOG_DIR}/${task_name}.stderr.log"
    info_file="${LOG_DIR}/${task_name}.info"
    status_file="${LOG_DIR}/${task_name}.exit_status"
    touch "${CSV_PATH}"
    start_line="$(wc -l < "${CSV_PATH}")"
    start_size="$(stat -c '%s' "${CSV_PATH}")"
    start_inode="$(stat -c '%i' "${CSV_PATH}")"

    printf 'task=%s\nstarted=%s\nslices=%s %s\nexpected_seeds=%s %s\ncsv_start_line=%s\ncsv_start_size=%s\ncsv_inode=%s\ncommand=%s\n' \
        "${task_name}" "$(date --iso-8601=seconds)" \
        "${first_slice}" "${second_slice}" "${first_seed}" "${second_seed}" \
        "${start_line}" "${start_size}" "${start_inode}" \
        "python tse.py --server 100 --problem UsCarrier.graphml --slices ${first_slice} ${second_slice} --tm-model generic --epsilon 0.1 --lambda 1" \
        > "${info_file}"

    printf '[%s] Starting task %d/9 (slices %s %s; seeds %s %s)\n' \
        "$(date --iso-8601=seconds)" "${task_no}" \
        "${first_slice}" "${second_slice}" "${first_seed}" "${second_seed}"

    setsid "${PYTHON_BIN}" tse.py \
        --server 100 \
        --problem UsCarrier.graphml \
        --slices "${first_slice}" "${second_slice}" \
        --tm-model generic \
        --epsilon 0.1 \
        --lambda 1 \
        > "${stdout_log}" 2> "${stderr_log}" &
    task_pid=$!
    task_sid="${task_pid}"
    printf 'pid=%s\nsid=%s\n' "${task_pid}" "${task_sid}" >> "${info_file}"

    csv_confirmed=0
    termination_requested=0
    validation_failure=0

    while process_is_live "${task_pid}"; do
        current_inode="$(stat -c '%i' "${CSV_PATH}" 2>/dev/null)"
        if [[ "${current_inode}" != "${start_inode}" ]]; then
            printf 'validation_error=CSV inode changed during task\n' >> "${info_file}"
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
           csv_handle_closed "${task_pid}"; then
            if ! sync -f "${CSV_PATH}"; then
                printf 'validation_error=tse.csv sync failed\n' >> "${info_file}"
                validation_failure=1
                break
            fi
            csv_confirmed=1
            csv_complete_time="$(date --iso-8601=seconds)"
            printf 'csv_complete=%s\ncsv_end_line=%s\ncsv_end_size=%s\n' \
                "${csv_complete_time}" "${current_line}" \
                "$(stat -c '%s' "${CSV_PATH}")" >> "${info_file}"

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

    if (( ! csv_confirmed )); then
        current_line="$(wc -l < "${CSV_PATH}")"
        if [[ "$(stat -c '%i' "${CSV_PATH}")" == "${start_inode}" ]] && \
           (( current_line - start_line == 3 )) && \
           validate_csv_append "${start_line}" "${first_seed}" "${second_seed}" && \
           sync -f "${CSV_PATH}"; then
            csv_confirmed=1
            printf 'csv_complete=%s\ncsv_end_line=%s\ncsv_end_size=%s\n' \
                "$(date --iso-8601=seconds)" "${current_line}" \
                "$(stat -c '%s' "${CSV_PATH}")" >> "${info_file}"
        fi
    fi

    printf '%s\n' "${rc}" > "${status_file}"
    printf 'process_exited=%s\nexit_status=%s\ntermination_requested=%s\n' \
        "$(date --iso-8601=seconds)" "${rc}" "${termination_requested}" \
        >> "${info_file}"

    if (( ! csv_confirmed || validation_failure )); then
        cp "${info_file}" "${LOG_DIR}/failed_command.info"
        printf 'batch_finished=%s\nexit_status=%s\nfailed_task=%s\nreason=CSV result could not be validated\n' \
            "$(date --iso-8601=seconds)" "${rc}" "${task_name}" \
            >> "${LOG_DIR}/batch.info"
        printf '[%s] Task %d/9 did not produce a validated complete result; stopping.\n' \
            "$(date --iso-8601=seconds)" "${task_no}" >&2
        exit 1
    fi

    if (( ! termination_requested && rc != 0 )); then
        cp "${info_file}" "${LOG_DIR}/failed_command.info"
        printf 'batch_finished=%s\nexit_status=%s\nfailed_task=%s\nreason=process exited abnormally\n' \
            "$(date --iso-8601=seconds)" "${rc}" "${task_name}" \
            >> "${LOG_DIR}/batch.info"
        printf '[%s] Task %d/9 exited abnormally with status %s; stopping.\n' \
            "$(date --iso-8601=seconds)" "${task_no}" "${rc}" >&2
        exit "${rc}"
    fi

    printf '[%s] Task %d/9 result persisted; process exited with status %s.\n' \
        "$(date --iso-8601=seconds)" "${task_no}" "${rc}"
done

printf 'batch_finished=%s\nexit_status=0\n' "$(date --iso-8601=seconds)" \
    >> "${LOG_DIR}/batch.info"
printf '[%s] All requested TSE tasks completed successfully.\n' \
    "$(date --iso-8601=seconds)"
