/**
 * K5/10-endpoint TE reconfiguration experiment with real RDMA NACK/GBN.
 *
 * The workload and all tunnels are converted from immutable MegaTE artifacts
 * by examples/k5-rdma-te/generate_manifest.py.  The only mutable forwarding
 * state is the exact (source,destination) entry on each source-site ingress.
 */
#include <algorithm>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "common.h"
#include "ns3/core-module.h"
#ifdef NS3_MTP
#include "ns3/mtp-interface.h"
#endif

using namespace ns3;
using namespace std;

namespace {

constexpr uint32_t kWindowBytes = 256 * 1024;
double g_teUpdateMs = 100.0;
const uint32_t kGateways[] = {0, 11, 22, 33, 44};

struct FlowRecord {
  uint32_t flowId = 0;
  uint32_t pairId = 0;
  uint32_t src = 0;
  uint32_t dst = 0;
  bool measurement = false;
  double demandMbps = 0;
  uint64_t wireRateBps = 0;
  uint64_t payloadBytes = 0;
  vector<uint32_t> oldTunnel;
  vector<uint32_t> newTunnel;
  string oldTunnelText;
  string newTunnelText;
  bool newMissing = false;
  double scheduledStartMs = 0;
  double actualStartMs = 0;
  double completionMs = 0;
  bool completed = false;
  uint64_t reorderedPackets = 0;
  uint64_t retransmittedPackets = 0;
  uint64_t uniquePayloadBytes = 0;
  uint64_t transmittedPayloadBytes = 0;
};

vector<FlowRecord> g_flows;
vector<Ptr<RdmaQueuePair>> g_qps;
string g_algorithm = "megate";
string g_manifest;
string g_csv;
string g_workloadSha;
uint32_t g_seed = 1;
uint32_t g_measurementTotal = 0;
uint32_t g_measurementFinished = 0;
uint32_t g_totalFinished = 0;

vector<string> Split(const string& input, char delimiter) {
  vector<string> fields;
  string field;
  istringstream stream(input);
  while (getline(stream, field, delimiter)) {
    if (!field.empty() && field.back() == '\r')
      field.pop_back();
    fields.push_back(field);
  }
  return fields;
}

vector<uint32_t> ParseTunnel(const string& input) {
  vector<uint32_t> result;
  for (const string& value : Split(input, ','))
    result.push_back(static_cast<uint32_t>(stoul(value)));
  return result;
}

uint32_t EndpointSite(uint32_t endpoint) {
  NS_ABORT_MSG_IF(endpoint == 0 || endpoint == 11 || endpoint == 22 ||
                      endpoint == 33 || endpoint == 44,
                  "gateway used as endpoint");
  return endpoint / 11;
}

void LoadManifest() {
  ifstream input(g_manifest);
  NS_ABORT_MSG_IF(!input, "cannot open workload manifest " << g_manifest);
  string line;
  getline(input, line);
  vector<string> header = Split(line, '\t');
  auto column = [&](const string& name) {
    auto it = find(header.begin(), header.end(), name);
    NS_ABORT_MSG_IF(it == header.end(), "manifest column missing: " << name);
    return static_cast<size_t>(it - header.begin());
  };
  const size_t newTunnelColumn = column(g_algorithm + "_tunnel");
  const size_t missingColumn = column(g_algorithm + "_missing");
  const size_t startColumn = column("start_ms_seed" + to_string(g_seed));
  while (getline(input, line)) {
    if (line.empty())
      continue;
    vector<string> value = Split(line, '\t');
    NS_ABORT_MSG_IF(value.size() != header.size(), "malformed manifest row");
    FlowRecord flow;
    flow.flowId = stoul(value[column("flow_id")]);
    flow.pairId = stoul(value[column("pair_id")]);
    flow.src = stoul(value[column("src")]);
    flow.dst = stoul(value[column("dst")]);
    flow.measurement = value[column("measurement")] == "1";
    flow.demandMbps = stod(value[column("demand_mbps")]);
    flow.wireRateBps = stoull(value[column("wire_rate_bps")]);
    flow.payloadBytes = stoull(value[column("payload_size_bytes")]);
    flow.oldTunnelText = value[column("old_tunnel")];
    flow.newTunnelText = value[newTunnelColumn];
    flow.oldTunnel = ParseTunnel(flow.oldTunnelText);
    flow.newTunnel = ParseTunnel(flow.newTunnelText);
    flow.newMissing = value[missingColumn] == "1";
    flow.scheduledStartMs = stod(value[startColumn]);
    NS_ABORT_MSG_IF(flow.flowId != g_flows.size(), "non-contiguous flow IDs");
    NS_ABORT_MSG_IF(flow.oldTunnel.size() < 2 || flow.newTunnel.size() < 2,
                    "invalid tunnel for flow " << flow.flowId);
    NS_ABORT_MSG_IF(flow.oldTunnel.front() != EndpointSite(flow.src) ||
                        flow.oldTunnel.back() != EndpointSite(flow.dst),
                    "old tunnel endpoints do not match flow " << flow.flowId);
    NS_ABORT_MSG_IF(flow.newTunnel.front() != EndpointSite(flow.src) ||
                        flow.newTunnel.back() != EndpointSite(flow.dst),
                    "new tunnel endpoints do not match flow " << flow.flowId);
    if (flow.measurement)
      g_measurementTotal++;
    g_flows.push_back(flow);
  }
  NS_ABORT_MSG_IF(g_flows.size() != 1981, "expected 1981 old-admitted flows");
  NS_ABORT_MSG_IF(g_measurementTotal != 52, "expected 52 measurement flows");
}

void SetTunnel(const FlowRecord& flow, const vector<uint32_t>& tunnel) {
  uint32_t sourceSite = EndpointSite(flow.src);
  uint32_t nextSite = tunnel.at(1);
  Ptr<Node> ingress = n.Get(kGateways[sourceSite]);
  Ptr<Node> next = n.Get(kGateways[nextSite]);
  NS_ABORT_MSG_IF(nbr2if[ingress].find(next) == nbr2if[ingress].end(),
                  "tunnel next hop is not a physical K5 neighbor");
  DynamicCast<SwitchNode>(ingress)->UpdatePairTableEntry(
      serverAddress[flow.src], serverAddress[flow.dst], nbr2if[ingress][next].idx);
}

void InstallOldTunnels() {
  for (const FlowRecord& flow : g_flows)
    SetTunnel(flow, flow.oldTunnel);
}

void ApplyTeUpdate() {
  uint32_t activeMeasurements = 0;
  uint32_t changedMeasurements = 0;
  for (const FlowRecord& flow : g_flows) {
    if (flow.measurement && !flow.completed)
      activeMeasurements++;
    if (flow.measurement && flow.oldTunnel != flow.newTunnel)
      changedMeasurements++;
    SetTunnel(flow, flow.newTunnel);
  }
  cout << "TE_UPDATE algorithm=" << g_algorithm
       << " time_ms=" << Simulator::Now().GetSeconds() * 1000.0
       << " active_measurements=" << activeMeasurements
       << " changed_measurements=" << changedMeasurements << endl;
  NS_ABORT_MSG_IF(activeMeasurements != g_measurementTotal,
                  "a measurement flow completed before the TE update");
}

static uint64_t RxKey(Ptr<RdmaQueuePair> qp) {
  return (static_cast<uint64_t>(qp->sip.Get()) << 32) |
         (static_cast<uint64_t>(qp->m_pg) << 16) | qp->sport;
}

void SnapshotFlow(FlowRecord& flow, Ptr<RdmaQueuePair> qp) {
  if (qp == nullptr)
    return;
  flow.retransmittedPackets = qp->m_retransmittedPackets;
  flow.uniquePayloadBytes = min<uint64_t>(qp->snd_una, flow.payloadBytes);
  flow.transmittedPayloadBytes = qp->m_transmittedPayloadBytes;
  Ptr<RdmaHw> receiver =
      n.Get(flow.dst)->GetObject<RdmaDriver>()->m_rdma;
  auto rx = receiver->m_rxQpMap.find(RxKey(qp));
  if (rx != receiver->m_rxQpMap.end())
    flow.reorderedPackets = rx->second->m_ooo_cnt;
}

void NoopNotify() {}
void QpFinish(FILE*, Ptr<RdmaQueuePair>) {}
void SendFinish(FILE*, Ptr<RdmaQueuePair>) {}

void MessageFinish(FILE*, Ptr<RdmaQueuePair> qp, uint64_t) {
  uint32_t id = static_cast<uint32_t>(qp->GetTag());
  FlowRecord& flow = g_flows.at(id);
  flow.completed = true;
  flow.completionMs = Simulator::Now().GetSeconds() * 1000.0;
  SnapshotFlow(flow, qp);
  g_totalFinished++;
  if (flow.measurement) {
    g_measurementFinished++;
    if (g_measurementFinished == g_measurementTotal)
      cout << "ALL_MEASUREMENTS_COMPLETE time_ms=" << flow.completionMs << endl;
  }
  if (g_totalFinished == g_flows.size()) {
    cout << "ALL_FLOWS_COMPLETE time_ms=" << flow.completionMs << endl;
    Simulator::Stop();
  }
}

void StartFlow(uint32_t id) {
  FlowRecord& flow = g_flows[id];
  uint16_t sport = portNumber[flow.src][flow.dst]++;
  Ptr<RdmaHw> hw = n.Get(flow.src)->GetObject<RdmaDriver>()->m_rdma;
  Ptr<RdmaQueuePair> qp = hw->AddQueuePair(
      flow.src, flow.dst, id, 0, 3, serverAddress[flow.src],
      serverAddress[flow.dst], sport, 100, kWindowBytes, 0,
      MakeCallback(&NoopNotify), MakeCallback(&NoopNotify));
  Ptr<ConstantRate> constant = DynamicCast<ConstantRate>(qp->m_congestionControl);
  NS_ABORT_MSG_IF(constant == nullptr, "CcMode 14 did not create ConstantRate");
  constant->SetRate(DataRate(flow.wireRateBps));
  qp->UpdateRate();
  g_qps[id] = qp;
  flow.actualStartMs = Simulator::Now().GetSeconds() * 1000.0;
  qp->PushMessage(flow.payloadBytes, MakeCallback(&NoopNotify),
                  MakeCallback(&NoopNotify));
  n.Get(flow.src)->GetObject<RdmaDriver>()->m_rdma->GetNicOfQp(qp)->TriggerTransmit();
}

string CsvQuote(const string& value) {
  return '"' + value + '"';
}

void WriteCsv() {
  bool header = static_cast<bool>(ifstream(g_csv));
  ofstream output(g_csv, ios::app);
  NS_ABORT_MSG_IF(!output, "cannot open output CSV " << g_csv);
  if (!header) {
    output << "algorithm,seed,workload_sha256,flow_id,pair_id,src,dst,measurement,"
              "old_tunnel,new_tunnel,new_route_missing,demand_mbps,"
              "configured_wire_rate_mbps,payload_size_bytes,unique_payload_bytes,"
              "actual_transmitted_data_bytes,reordered_packets,retransmitted_packets,"
              "start_time_ms,completion_time_ms,fct_ms,completed\n";
  }
  for (uint32_t id = 0; id < g_flows.size(); id++) {
    FlowRecord& flow = g_flows[id];
    SnapshotFlow(flow, g_qps[id]);
    if (flow.measurement && !flow.completed && g_qps[id] != nullptr) {
      Ptr<RdmaQueuePair> qp = g_qps[id];
      cout << "INCOMPLETE flow=" << id << " src=" << flow.src
           << " dst=" << flow.dst << " snd_una=" << qp->snd_una
           << " snd_nxt=" << qp->snd_nxt
           << " high=" << qp->m_highestSentSeq
           << " onfly=" << qp->GetOnTheFly()
           << " next_avail_ns=" << qp->m_nextAvail.GetNanoSeconds()
           << " now_ns=" << Simulator::Now().GetNanoSeconds() << endl;
    }
    output << g_algorithm << ',' << g_seed << ',' << g_workloadSha << ','
           << flow.flowId << ',' << flow.pairId << ',' << flow.src << ','
           << flow.dst << ',' << flow.measurement << ','
           << CsvQuote(flow.oldTunnelText) << ',' << CsvQuote(flow.newTunnelText)
           << ',' << flow.newMissing << ',' << fixed << setprecision(12)
           << flow.demandMbps << ',' << setprecision(6)
           << flow.wireRateBps / 1e6 << ',' << flow.payloadBytes << ','
           << flow.uniquePayloadBytes << ',' << flow.transmittedPayloadBytes << ','
           << flow.reorderedPackets << ',' << flow.retransmittedPackets << ','
           << setprecision(9) << flow.actualStartMs << ',';
    if (flow.completed) {
      double fct = flow.completionMs - flow.actualStartMs;
      output << flow.completionMs << ',' << fct;
    } else {
      output << ',';
    }
    output << ',' << flow.completed << '\n';
  }
  uint64_t drops = 0;
  for (uint32_t id : kGateways)
    drops += DynamicCast<SwitchNode>(n.Get(id))->GetDroppedPackets();
  cout << "NETWORK_DROPS packets=" << drops << endl;
}

} // namespace

int main(int argc, char* argv[]) {
#ifdef NS3_MTP
  // Keep the mtp library linked because RDMA objects use its lightweight
  // critical-section symbols, but run this reproducibility experiment on the
  // deterministic single-thread simulator.
  (void)MtpInterface::isEnabled();
#endif
  CommandLine cmd;
  cmd.AddValue("algorithm", "gurobi, tse, or megate", g_algorithm);
  cmd.AddValue("seed", "workload/RNG seed (1..5)", g_seed);
  cmd.AddValue("manifest", "shared workload TSV", g_manifest);
  cmd.AddValue("csv", "raw per-flow CSV", g_csv);
  cmd.AddValue("workloadSha", "validated manifest SHA-256", g_workloadSha);
  cmd.AddValue("teUpdateMs", "TE update time in milliseconds", g_teUpdateMs);
  cmd.Parse(argc, argv);
  NS_ABORT_MSG_IF(g_algorithm != "gurobi" && g_algorithm != "tse" &&
                      g_algorithm != "megate",
                  "invalid algorithm");
  NS_ABORT_MSG_IF(g_seed < 1 || g_seed > 5, "seed must be in [1,5]");
  NS_ABORT_MSG_IF(g_manifest.empty() || g_csv.empty(),
                  "--manifest and --csv are required");
  NS_ABORT_MSG_IF(g_teUpdateMs <= 0.0, "--teUpdateMs must be positive");

  RngSeedManager::SetSeed(g_seed);
  RngSeedManager::SetRun(g_seed);
  LoadManifest();
  if (!ReadConf(argc, argv))
    return 1;
  cout << "OUTPUT_PATHS qlen=" << qlen_mon_file << " bw=" << bw_mon_file
       << " rate=" << rate_mon_file << " cnp=" << cnp_mon_file << endl;
  SetConfig();
  SetupNetwork(QpFinish, SendFinish, MessageFinish);
  InstallOldTunnels();

  g_qps.resize(g_flows.size());
  for (uint32_t id = 0; id < g_flows.size(); id++) {
    Simulator::Schedule(Seconds(g_flows[id].scheduledStartMs / 1000.0), StartFlow, id);
  }
  Simulator::Schedule(Seconds(g_teUpdateMs / 1000.0), ApplyTeUpdate);
  Simulator::Stop(Seconds(simulator_stop_time));
  cout << "RUN algorithm=" << g_algorithm << " seed=" << g_seed
       << " flows=" << g_flows.size() << " measurements=" << g_measurementTotal
       << endl;
  Simulator::Run();
  WriteCsv();
  cout << "RESULT algorithm=" << g_algorithm << " seed=" << g_seed
       << " measurements_finished=" << g_measurementFinished << '/'
       << g_measurementTotal << " all_flows_finished=" << g_totalFinished << '/'
       << g_flows.size() << endl;
  Simulator::Destroy();
  return g_totalFinished == g_flows.size() ? 0 : 2;
}
