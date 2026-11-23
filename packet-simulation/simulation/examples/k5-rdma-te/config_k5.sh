# K5 RDMA TE-reconfiguration experiment.
TOPOLOGY_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/k5-rdma-te/topology.txt
FLOW_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/k5-rdma-te/empty_flows.txt

FCT_OUTPUT_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/k5-rdma-te/outputs/common_fct.txt
PFC_OUTPUT_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/k5-rdma-te/outputs/common_pfc.txt
SEND_OUTPUT_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/k5-rdma-te/outputs/common_send.txt
QLEN_MON_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/k5-rdma-te/outputs/common_qlen.txt
BW_MON_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/k5-rdma-te/outputs/common_bw.txt
RATE_MON_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/k5-rdma-te/outputs/common_rate.txt
CNP_MON_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/k5-rdma-te/outputs/common_cnp.txt

ENABLE_TRACE 0
TRACE_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/k5-rdma-te/trace_config.txt
TRACE_OUTPUT_FILE /home/zyxl/ns-3-alibabacloud/simulation/examples/k5-rdma-te/outputs/common_mix.tr

SIMULATOR_STOP_TIME 5.0
ERROR_RATE_PER_LINK 0.0
HAS_WIN 1
GLOBAL_T 0
INT_MULTI 1
PINT_LOG_BASE 1.05
ACK_HIGH_PRIO 1
LINK_DOWN 0 0 0
BUFFER_SIZE 32

MON_START 6000000
MON_END 7000000
QP_MON_INTERVAL 100
QLEN_MON_INTERVAL 100
BW_MON_INTERVAL 1000

KMAX_MAP 2 1000000000 1600 100000000000 1600
KMIN_MAP 2 1000000000 400 100000000000 400
PMAX_MAP 2 1000000000 0.2 100000000000 0.2

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
ns3::RdmaHw::NackEnabled true
ns3::RdmaHw::NACKGenerationInterval 500.0
ns3::RdmaEgressQueue::TokenPerRound 1076
