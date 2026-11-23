# TE Reconfiguration -> Packet Reordering experiment (100 endpoint pairs)

# INPUT FILE PATH
TOPOLOGY_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/te-reorder/topo_te_reorder.txt
FLOW_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/te-reorder/flows_100pairs.txt

# OUTPUT FILE PATH
FCT_OUTPUT_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/te-reorder/outputs/fct.txt
PFC_OUTPUT_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/te-reorder/outputs/pfc.txt

# MONITOR SETTINGS (start after the 1.3s simulation stop => monitors stay silent)
QLEN_MON_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/te-reorder/outputs/qlen.txt
BW_MON_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/te-reorder/outputs/bw.txt
RATE_MON_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/te-reorder/outputs/rate.txt
CNP_MON_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/te-reorder/outputs/cnp.txt
MON_START 2000000
MON_END 3000000
QP_MON_INTERVAL 100
QLEN_MON_INTERVAL 100
BW_MON_INTERVAL 1000

# TRACE SETTINGS
ENABLE_TRACE 0
TRACE_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/te-reorder/trace_config.txt
TRACE_OUTPUT_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/te-reorder/outputs/mix.tr

# VAR SETTINGS
SIMULATOR_STOP_TIME 1.3
ERROR_RATE_PER_LINK 0.0000

HAS_WIN 1
GLOBAL_T 0

INT_MULTI 1
PINT_LOG_BASE 1.05

ACK_HIGH_PRIO 0

LINK_DOWN 0 0 0

# one entry for the 100Gbps links (SetupNetwork asserts kmin/kmax/pmax per port speed)
KMAX_MAP 1 100000000000 1600
KMIN_MAP 1 100000000000 400
PMAX_MAP 1 100000000000 0.2

BUFFER_SIZE 32

# NS3 SETTINGS
ns3::QbbNetDevice::QcnEnabled false
ns3::QbbNetDevice::DynamicThreshold true

ns3::SwitchNode::PfcEnabled false

ns3::RdmaHw::Mtu 1024
ns3::RdmaHw::CcMode 14
ns3::RdmaHw::RateBound true
ns3::RdmaHw::VarWin false
ns3::RdmaHw::L2ChunkSize 1024
ns3::RdmaHw::L2AckInterval 1
ns3::RdmaHw::L2BackToZero false
ns3::RdmaHw::NackEnabled false
ns3::RdmaHw::NACKGenerationInterval 10000.0

# fixed per-QP sending rate; wire-rate value so that the payload rate is 250Mbps
# (wire size 1076B = 1024B payload + 52B headers, measured in Phase A)
ns3::ConstantRate::Rate 262.7Mb/s

# pace one packet per DWRR round instead of 4000B bursts
ns3::RdmaEgressQueue::TokenPerRound 1076
