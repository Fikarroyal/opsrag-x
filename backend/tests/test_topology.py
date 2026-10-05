from app.investigation.topology import TopologyGraph, analyze_scope


def topo(settings):
    return TopologyGraph.load(settings.raw_dir / "network_topology.json")


def test_path_matches_documented_topology(settings):
    t = topo(settings)
    assert t.path("PC-POLI3-001", "SIMRS-APP-01") == ["PC-POLI3-001", "SW-POLI3", "SW-DIST-01", "CORE-SW-01", "RTR-CORE", "SIMRS-APP-01"]
    assert t.path("PC-LAB-001", "DNS-01")[1:3] == ["SW-LAB", "SW-DIST-02"]
    assert t.path("PC-POLI3-001", "NOPE") is None


def test_access_uplink_and_endpoints(settings):
    t = topo(settings)
    assert t.access_switch("PC-POLI3-005") == "SW-POLI3" and t.dist_switch("SW-POLI3") == "SW-DIST-01"
    assert t.uplink("SW-POLI3") == {"interface": "Gi0/48", "peer": "SW-DIST-01", "peer_interface": t.uplink("SW-POLI3")["peer_interface"]}
    assert len(t.endpoints_of("SW-POLI3")) == 13  # 12 PCs + 1 printer


def test_scope_single_switch_unit(settings):
    sc = analyze_scope(topo(settings), ["PC-POLI3-001", "PC-POLI3-002", "PC-POLI3-003"], ["Poli 3"], None)
    assert sc.shared_access_switch == "SW-POLI3" and sc.scope_level == "single_unit" and len(sc.peers_healthy) == 10


def test_scope_single_device_and_wide(settings):
    t = topo(settings)
    assert analyze_scope(t, ["PC-KASIR-003"], ["Kasir"], None).scope_level == "single_device"
    wide = analyze_scope(t, ["PC-POLI3-001", "PC-KASIR-001"], ["Poli 3", "Kasir", "IGD"], None)
    assert wide.scope_level == "hospital_wide" and wide.shared_access_switch is None and len(wide.access_groups) == 2
    assert analyze_scope(t, [], [], "single_unit").scope_level == "single_unit"
