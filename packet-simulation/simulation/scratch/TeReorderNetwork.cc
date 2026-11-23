/**
 * TE Reconfiguration -> RDMA Packet Reordering experiment.
 *
 * Topology:
 *   100 src hosts (0..99)   -- SW1 (200)
 *   100 dst hosts (100..199) -- SW3 (202)
 *   SW2 (201) sits between SW1 and SW3.
 *   Old tunnel: SW1 -> SW2 -> SW3, one-way propagation 2ms (RTT ~4ms)
 *   New tunnel: SW1 -> SW3,        one-way propagation 1ms (RTT ~2ms)
 *
 * 100 one-to-one endpoint pairs, each with a single QP sending one large
 * message at a fixed rate (CcMode 14 = ConstantRate, payload 250Mbps).
 * At t=0.5s the TE controller moves the first N pairs to the new tunnel by
 * rewriting the real switch forwarding tables (UpdateTableEntry). Packets
 * already in flight keep their old path; ACKs follow the pair's current
 * tunnel. The receiver counts packets arriving with PSN > ExpectedPSN
 * (buffered in a reorder buffer; NACK and go-back-N are disabled for this
 * experiment via ns3::RdmaHw::NackEnabled=false).
 */
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>
#include "common.h"
#include "ns3/core-module.h"
#ifdef NS3_MTP
#include "ns3/mtp-interface.h"
#endif

using namespace std;
using namespace ns3;

// ---- experiment constants ----
static const uint32_t SRC_BASE = 0;
static const uint32_t DST_BASE = 100;
static const uint32_t SW1_ID = 200;
static const uint32_t SW2_ID = 201;
static const uint32_t SW3_ID = 202;
static const uint64_t WIN_BYTES = 256 * 1024;  // 256 max outstanding packets
static const double TE_UPDATE_TIME = 0.5;      // seconds
// simulation stop time comes from the config file (SIMULATOR_STOP_TIME)
// instead of a hardcoded constant, so there is a single source of truth.

// ---- experiment variables ----
static uint32_t g_nReassigned = 30;
static uint32_t g_seed = 1;
static string g_csvPath;

struct FlowEntry {
  uint32_t src, dst, pg, dport;
  uint64_t bytes;
  double start;
};
static vector<FlowEntry> g_flows;
static vector<Ptr<RdmaQueuePair>> g_qps;
static uint32_t g_msgFinished = 0;
static EventId g_progressEvent;

static void NoopNotify() {}

// progress heartbeat for debugging: how fast does sim time advance?
static void Progress() {
  cout << "[progress] t=" << fixed << setprecision(6)
       << Simulator::Now().GetSeconds() << "s" << endl;
  g_progressEvent = Simulator::Schedule(MilliSeconds(50), Progress);
}

/************************************************
 * TE controller: PairID -> CurrentTunnelID
 * Implemented on the real switch forwarding tables:
 *   SW1 routes each dst host (data path),
 *   SW3 routes each src host (ACK path).
 ***********************************************/
static void TeSetTunnel(uint32_t pair, bool useNewTunnel) {
  Ptr<Node> sw1 = n.Get(SW1_ID), sw2 = n.Get(SW2_ID), sw3 = n.Get(SW3_ID);
  Ipv4Address dstAddr = serverAddress[g_flows[pair].dst];
  Ipv4Address srcAddr = serverAddress[g_flows[pair].src];
  // data path: SW1 -> dst host
  Ptr<Node> fwdNext = useNewTunnel ? sw3 : sw2;
  DynamicCast<SwitchNode>(sw1)
      ->UpdateTableEntry(dstAddr, nbr2if[sw1][fwdNext].idx);
  // ACK path: SW3 -> src host
  Ptr<Node> revNext = useNewTunnel ? sw1 : sw2;
  DynamicCast<SwitchNode>(sw3)
      ->UpdateTableEntry(srcAddr, nbr2if[sw3][revNext].idx);
}

static void TeApplyAll(uint32_t nReassigned) {
  for (uint32_t i = 0; i < g_flows.size(); i++)
    TeSetTunnel(i, i < nReassigned);
  cout << "TE update at " << Simulator::Now().GetSeconds()
       << "s: " << nReassigned << " pairs -> new tunnel, "
       << (g_flows.size() - min<size_t>(nReassigned, g_flows.size()))
       << " pairs stay on old tunnel" << endl;
}

/************************************************
 * QP and traffic setup: one QP per endpoint pair
 ***********************************************/
static void CreateQp(uint32_t pair) {
  FlowEntry& f = g_flows[pair];
  uint32_t sport = portNumber[f.src][f.dst]++;  // fresh port per pair
  Ptr<RdmaDriver> rdma = n.Get(f.src)->GetObject<RdmaDriver>();
  Ptr<RdmaQueuePair> qp = rdma->AddQueuePair(
      f.src, f.dst, pair + 1, 0 /*create the qp without a message*/, f.pg,
      serverAddress[f.src], serverAddress[f.dst], sport, f.dport, WIN_BYTES,
      0 /*baseRtt, unused by ConstantRate*/,
      MakeCallback(&NoopNotify), MakeCallback(&NoopNotify));
  g_qps.push_back(qp);
}

static void StartFlow(uint32_t pair) {
  FlowEntry& f = g_flows[pair];
  Ptr<RdmaQueuePair> qp = g_qps[pair];
  qp->PushMessage(
      f.bytes, MakeCallback(&NoopNotify), MakeCallback(&NoopNotify));
  Ptr<RdmaDriver> rdma = n.Get(f.src)->GetObject<RdmaDriver>();
  rdma->m_rdma->GetNicOfQp(qp)->TriggerTransmit();
}

/************************************************
 * completion callbacks wired via RdmaDriver traces
 ***********************************************/
static void FinishAll() {
  Simulator::Cancel(g_progressEvent);
  for (auto& qp : g_qps) {
    Ptr<RdmaDriver> rdma = n.Get(qp->m_src)->GetObject<RdmaDriver>();
    rdma->FinishQueuePair(qp);
  }
  cancel_monitor();
}

static void qp_finish(FILE* fout, Ptr<RdmaQueuePair> q) {
  uint32_t did = ip_to_node_id(q->dip);
  Ptr<RdmaDriver> rdma = n.Get(did)->GetObject<RdmaDriver>();
  rdma->m_rdma->DeleteRxQp(q->sip.Get(), q->m_pg, q->sport);
}

static void send_finish(FILE* fout, Ptr<RdmaQueuePair> q) {
  // nothing to do for this experiment
}

static void message_finish(FILE* fout, Ptr<RdmaQueuePair> q, uint64_t msgSize) {
  uint32_t sid = ip_to_node_id(q->sip), did = ip_to_node_id(q->dip);
  // per-pair reorder count from the receiver's rxQp (alive until FinishAll)
  Ptr<RdmaHw> dstRdma = n.Get(did)->GetObject<RdmaDriver>()->m_rdma;
  uint64_t key = ((uint64_t)q->sip.Get() << 32) |
                 ((uint64_t)q->m_pg << 16) | (uint64_t)q->sport;
  auto it = dstRdma->m_rxQpMap.find(key);
  uint64_t ooo = it == dstRdma->m_rxQpMap.end() ? 0 : it->second->m_ooo_cnt;
  cout << "message finish at " << Simulator::Now().GetSeconds() << "s, pair "
       << sid - SRC_BASE << " (" << sid << "->" << did << "): " << msgSize
       << " bytes, " << ooo << " reordered packets" << endl;
  g_msgFinished++;
  if (g_msgFinished == g_flows.size())
    FinishAll();
}

/************************************************
 * summary: one CSV row per simulation run
 ***********************************************/
static void WriteCsv() {
  uint64_t total = 0;
  for (uint32_t i = 0; i < n.GetN(); i++) {
    if (n.Get(i)->GetNodeType() == 0)  // host
      total += n.Get(i)->GetObject<RdmaDriver>()->m_rdma->m_ooo_pkt_cnt;
  }
  bool complete = g_msgFinished == g_flows.size();
  cout << "RESULT seed=" << g_seed << " reassigned_pairs=" << g_nReassigned
       << " reordered_packets=" << total << " messages_finished="
       << g_msgFinished << "/" << g_flows.size() << endl;
  if (!complete)
    cerr << "WARNING: simulation stopped with only " << g_msgFinished << "/"
         << g_flows.size()
         << " messages finished; the CSV row below is from an INCOMPLETE run"
         << endl;

  // rxQps whose reorder buffer is still non-empty at stop time indicate a
  // permanent gap (e.g. a lost packet with NACK disabled): those buffered
  // packets were counted as "reordered" but will never be delivered in order.
  uint32_t stuckQps = 0;
  for (uint32_t i = 0; i < n.GetN(); i++) {
    if (n.Get(i)->GetNodeType() != 0)
      continue;
    Ptr<RdmaHw> rdma = n.Get(i)->GetObject<RdmaDriver>()->m_rdma;
    for (auto& kv : rdma->m_rxQpMap)
      if (!kv.second->m_reorderBuf.empty())
        stuckQps++;
  }
  if (stuckQps > 0)
    cerr << "WARNING: " << stuckQps
         << " rxQps still hold buffered out-of-order packets at stop time"
         << " (possible permanent gap / lost packet); their reorder counts are"
         << " contaminated" << endl;

  if (g_csvPath.empty())
    return;
  ifstream exist(g_csvPath);
  bool hasHeader = exist.good();
  exist.close();
  ofstream csv(g_csvPath, ios::app);
  if (!hasHeader)
    csv << "seed,reassigned_pairs,reordered_packets" << endl;
  csv << g_seed << "," << g_nReassigned << "," << total << endl;
}

int main(int argc, char* argv[]) {
#ifdef NS3_MTP
  MtpInterface::Enable(16);
#endif
  CommandLine cmd;
  cmd.AddValue(
      "Nreassigned",
      "Number of endpoint pairs moved to the new tunnel at the TE update",
      g_nReassigned);
  cmd.AddValue("seed", "RNG seed (recorded in the CSV)", g_seed);
  cmd.AddValue("csv", "Path of the summary CSV (a row is appended)", g_csvPath);
  cmd.Parse(argc, argv);
  RngSeedManager::SetSeed(g_seed);

  if (!ReadConf(argc, argv))
    return -1;
  SetConfig();
  SetupNetwork(qp_finish, send_finish, message_finish);

  // read the whole flow list (the count line was consumed by SetupNetwork)
  g_flows.reserve(flow_num);
  for (uint32_t i = 0; i < flow_num; i++) {
    FlowEntry f;
    flowf >> f.src >> f.dst >> f.pg >> f.dport >> f.bytes >> f.start;
    NS_ASSERT(
        n.Get(f.src)->GetNodeType() == 0 &&
        n.Get(f.dst)->GetNodeType() == 0);
    g_flows.push_back(f);
  }
  flowf.close();
  cout << "Flow num: " << g_flows.size()
       << ", N_reassigned: " << g_nReassigned << endl;

  // initial tunnel assignment: everyone on the old (long) tunnel,
  // overriding the shortest-path tables installed by SetupNetwork
  TeApplyAll(0);
  // the real TE update at t=0.5s
  Simulator::Schedule(Seconds(TE_UPDATE_TIME), TeApplyAll, g_nReassigned);

  // create one QP per pair and schedule its single message
  for (uint32_t i = 0; i < g_flows.size(); i++) {
    CreateQp(i);
    Simulator::Schedule(Seconds(g_flows[i].start), StartFlow, i);
  }

  cout << "Running Simulation." << endl;
  g_progressEvent = Simulator::Schedule(MilliSeconds(50), Progress);
  Simulator::Stop(Seconds(simulator_stop_time));
  Simulator::Run();
  // collect results while the node objects are guaranteed alive,
  // i.e. before Simulator::Destroy()
  WriteCsv();
  Simulator::Destroy();

  return 0;
}
