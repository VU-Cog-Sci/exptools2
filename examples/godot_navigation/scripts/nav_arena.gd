extends Node3D


var udp := PacketPeerUDP.new()
var listen_host: String = "127.0.0.1"
var listen_port: int = 5005
var peer_ip: String = ""
var peer_port: int = -1

var run_payload: Dictionary = {}
var run_condition: Dictionary = {}
var run_id: String = "sub-000_ses-00_task-navarena_run-00"
var output_dir: String = "user://runs"
var running: bool = false

var rng := RandomNumberGenerator.new()

var arena_radius: float = 12.0
var wall_height: float = 1.4
var mountain_distance: float = 80.0
var run_duration_s: float = 180.0
var player_speed: float = 4.5
var turn_speed: float = 1.9
var collection_radius: float = 1.0
var default_num_gems: int = 8
var reward_min: int = 1
var reward_max: int = 5
var default_show_gems: bool = false
var auto_quit: bool = true

var player_pos: Vector3 = Vector3(0.0, 1.65, 0.0)
var player_yaw: float = 0.0
var player_speed_m_s: float = 0.0
var score: float = 0.0
var phase_elapsed_s: float = 0.0
var trial_elapsed_s: float = 0.0
var next_sync_s: float = 0.0

var trial_plan: Array = []
var trial_index: int = -1

var frame_trace: Array = []
var gems: Array = []
var gem_events: Array = []

var camera: Camera3D
var floor_mesh: MeshInstance3D
var wall_mesh: MeshInstance3D
var mountain_root: Node3D
var gem_root: Node3D


func _ready() -> void:
    _parse_cli_args()
    _setup_scene_graph()
    _apply_condition({})
    _reset_run_state()

    var err := udp.bind(listen_port, listen_host)
    if err != OK:
        push_error("Could not bind UDP listener on %s:%d" % [listen_host, listen_port])
    else:
        print("Navigation arena listening on %s:%d" % [listen_host, listen_port])


func _physics_process(delta: float) -> void:
    _poll_udp()
    if not running:
        return

    if Input.is_key_pressed(KEY_ESCAPE):
        _finish_run("aborted")
        return

    var trial := _active_trial()
    if trial.is_empty():
        _finish_run("ok")
        return

    if bool(trial.get("allow_movement", true)):
        _update_navigation(delta)
    else:
        player_speed_m_s = 0.0

    if bool(trial.get("allow_collection", true)):
        _collect_gems()

    trial_elapsed_s += delta
    phase_elapsed_s += delta
    _record_frame()

    var trial_duration := float(trial.get("duration_s", 0.1))
    if trial_elapsed_s >= trial_duration:
        _start_trial(trial_index + 1)


func _parse_cli_args() -> void:
    var args: PackedStringArray = OS.get_cmdline_user_args()
    var idx := 0
    while idx < args.size():
        var token := str(args[idx])
        if token == "--godot-host" and idx + 1 < args.size():
            listen_host = str(args[idx + 1])
            idx += 2
            continue
        if token == "--godot-port" and idx + 1 < args.size():
            listen_port = int(args[idx + 1])
            idx += 2
            continue
        if token == "--output-dir" and idx + 1 < args.size():
            output_dir = str(args[idx + 1])
            idx += 2
            continue
        if token == "--no-auto-quit":
            auto_quit = false
            idx += 1
            continue
        idx += 1


func _setup_scene_graph() -> void:
    var environment_node := WorldEnvironment.new()
    var environment := Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = Color(0.62, 0.75, 0.92, 1.0)
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color(0.92, 0.92, 0.95, 1.0)
    environment.ambient_light_energy = 0.5
    environment_node.environment = environment
    add_child(environment_node)

    var sun := DirectionalLight3D.new()
    sun.light_energy = 1.8
    sun.rotation = Vector3(deg_to_rad(-48.0), deg_to_rad(35.0), 0.0)
    add_child(sun)

    camera = Camera3D.new()
    camera.current = true
    camera.fov = 80.0
    camera.position = player_pos
    add_child(camera)

    floor_mesh = MeshInstance3D.new()
    add_child(floor_mesh)

    wall_mesh = MeshInstance3D.new()
    add_child(wall_mesh)

    mountain_root = Node3D.new()
    mountain_root.name = "Mountains"
    add_child(mountain_root)

    gem_root = Node3D.new()
    gem_root.name = "Gems"
    add_child(gem_root)


func _apply_condition(condition: Dictionary) -> void:
    run_condition = condition.duplicate(true)

    arena_radius = float(run_condition.get("arena_radius", 12.0))
    wall_height = float(run_condition.get("wall_height", 1.4))
    mountain_distance = float(run_condition.get("mountain_distance", 80.0))
    run_duration_s = float(run_condition.get("duration_s", run_condition.get("run_duration_s", 180.0)))
    player_speed = float(run_condition.get("player_speed", 4.5))
    turn_speed = float(run_condition.get("turn_speed", 1.9))
    collection_radius = float(run_condition.get("collection_radius", 1.0))
    default_num_gems = int(run_condition.get("num_gems", 8))
    reward_min = int(run_condition.get("reward_min", 1))
    reward_max = int(run_condition.get("reward_max", 5))
    default_show_gems = bool(run_condition.get("show_gems", false))
    auto_quit = bool(run_condition.get("auto_quit", auto_quit))

    _build_arena()
    _build_mountains()

    trial_plan = _resolve_trial_plan(run_condition)
    var total_s := 0.0
    for item in trial_plan:
        if typeof(item) == TYPE_DICTIONARY:
            total_s += float(item.get("duration_s", 0.0))
    if total_s > 0.0:
        run_duration_s = total_s


func _resolve_trial_plan(condition: Dictionary) -> Array:
    var structure = condition.get("trial_structure", [])
    var out: Array = []

    if typeof(structure) == TYPE_ARRAY:
        for idx in range(structure.size()):
            if typeof(structure[idx]) != TYPE_DICTIONARY:
                continue
            var raw: Dictionary = structure[idx]
            var mode := str(raw.get("mode", "search")).to_lower()
            var item: Dictionary = {
                "name": str(raw.get("name", "trial_%02d" % idx)),
                "mode": mode,
                "duration_s": max(0.1, float(raw.get("duration_s", 30.0))),
                "num_gems": int(raw.get("num_gems", default_num_gems)),
                "show_gems": bool(raw.get("show_gems", mode == "encoding" or default_show_gems)),
                "reset_gems": bool(raw.get("reset_gems", idx == 0 or mode == "encoding")),
                "allow_movement": bool(raw.get("allow_movement", mode != "rest")),
                "allow_collection": bool(
                    raw.get("allow_collection", mode in ["search", "forage", "probe", "retrieval"])
                ),
            }
            out.append(item)

    if out.is_empty():
        out.append(
            {
                "name": "navigation",
                "mode": "search",
                "duration_s": max(0.1, run_duration_s),
                "num_gems": default_num_gems,
                "show_gems": default_show_gems,
                "reset_gems": true,
                "allow_movement": true,
                "allow_collection": true,
            }
        )

    return out


func _build_arena() -> void:
    var floor_cyl := CylinderMesh.new()
    floor_cyl.top_radius = arena_radius
    floor_cyl.bottom_radius = arena_radius
    floor_cyl.height = 0.06
    floor_cyl.radial_segments = 96
    floor_mesh.mesh = floor_cyl
    floor_mesh.position = Vector3(0.0, -0.03, 0.0)
    floor_mesh.material_override = _new_material(Color(0.67, 0.67, 0.69, 1.0), 0.95, 0.0)

    var wall_cyl := CylinderMesh.new()
    wall_cyl.top_radius = arena_radius + 0.15
    wall_cyl.bottom_radius = arena_radius + 0.15
    wall_cyl.height = wall_height
    wall_cyl.radial_segments = 96
    wall_mesh.mesh = wall_cyl
    wall_mesh.position = Vector3(0.0, wall_height * 0.5, 0.0)
    wall_mesh.material_override = _new_material(Color(0.92, 0.95, 1.0, 0.22), 0.2, 0.0, true)


func _build_mountains() -> void:
    for child in mountain_root.get_children():
        child.queue_free()

    var cues := [
        {"name": "North Peak", "angle_deg": 0.0, "height": 24.0, "color": Color(0.18, 0.34, 0.56, 1.0)},
        {"name": "East Twin", "angle_deg": 90.0, "height": 20.0, "color": Color(0.42, 0.28, 0.20, 1.0)},
        {"name": "South Ridge", "angle_deg": 180.0, "height": 27.0, "color": Color(0.16, 0.44, 0.36, 1.0)},
        {"name": "West Tooth", "angle_deg": 270.0, "height": 22.0, "color": Color(0.50, 0.22, 0.26, 1.0)},
        {"name": "NE Spur", "angle_deg": 45.0, "height": 18.0, "color": Color(0.30, 0.30, 0.58, 1.0)},
        {"name": "SE Spur", "angle_deg": 135.0, "height": 16.0, "color": Color(0.54, 0.36, 0.18, 1.0)},
        {"name": "SW Spur", "angle_deg": 225.0, "height": 17.0, "color": Color(0.26, 0.45, 0.24, 1.0)},
        {"name": "NW Spur", "angle_deg": 315.0, "height": 19.0, "color": Color(0.46, 0.28, 0.42, 1.0)},
    ]

    for cue in cues:
        var cluster := Node3D.new()
        cluster.name = str(cue["name"])
        mountain_root.add_child(cluster)

        var angle := deg_to_rad(float(cue["angle_deg"]))
        var direction := Vector3(sin(angle), 0.0, cos(angle))
        var base := direction * mountain_distance
        var color: Color = cue["color"]
        var height := float(cue["height"])

        for n in range(3):
            var peak := MeshInstance3D.new()
            var mesh := CylinderMesh.new()
            mesh.top_radius = 0.05 + n * 0.05
            mesh.bottom_radius = 3.0 + n * 1.2
            mesh.height = height - n * 2.8
            mesh.radial_segments = 24
            peak.mesh = mesh
            peak.material_override = _new_material(color.darkened(0.1 * n), 0.85, 0.0)

            var tangent := Vector3(direction.z, 0.0, -direction.x)
            peak.position = base + tangent * float(n - 1) * 4.5
            peak.position.y = mesh.height * 0.5 - 0.05
            cluster.add_child(peak)

        var label := Label3D.new()
        label.text = str(cue["name"])
        label.font_size = 36
        label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
        label.position = base + Vector3(0.0, height + 2.0, 0.0)
        label.modulate = Color(0.94, 0.96, 1.0, 0.8)
        cluster.add_child(label)


func _spawn_gems(num: int, visible: bool) -> void:
    for child in gem_root.get_children():
        child.queue_free()
    gems.clear()

    for i in range(num):
        var loc2 := _sample_in_disc(arena_radius * 0.72)
        var reward := rng.randi_range(reward_min, reward_max)
        var marker := MeshInstance3D.new()
        var sphere := SphereMesh.new()
        sphere.radius = 0.22
        marker.mesh = sphere
        marker.position = Vector3(loc2.x, 0.24, loc2.y)
        marker.visible = visible
        marker.material_override = _new_material(Color(1.0, 0.84, 0.30, 1.0), 0.15, 0.3)
        gem_root.add_child(marker)

        gems.append(
            {
                "id": i,
                "position": loc2,
                "reward": reward,
                "found": false,
                "marker": marker,
            }
        )


func _set_gem_visibility(visible: bool) -> void:
    for idx in range(gems.size()):
        var gem: Dictionary = gems[idx]
        var marker: MeshInstance3D = gem.get("marker")
        if marker != null:
            marker.visible = visible and (not bool(gem.get("found", false)))


func _sample_in_disc(radius: float) -> Vector2:
    var t := rng.randf() * TAU
    var u := sqrt(rng.randf()) * radius
    return Vector2(cos(t) * u, sin(t) * u)


func _reset_run_state() -> void:
    player_pos = Vector3(0.0, 1.65, 0.0)
    player_yaw = 0.0
    player_speed_m_s = 0.0
    score = 0.0
    phase_elapsed_s = 0.0
    trial_elapsed_s = 0.0
    next_sync_s = 0.0
    trial_index = -1
    frame_trace.clear()
    gem_events.clear()

    if camera != null:
        camera.position = player_pos
        camera.rotation = Vector3.ZERO


func _poll_udp() -> void:
    while udp.get_available_packet_count() > 0:
        var packet: PackedByteArray = udp.get_packet()
        var decoded = JSON.parse_string(packet.get_string_from_utf8())
        if typeof(decoded) != TYPE_DICTIONARY:
            continue
        var msg: Dictionary = decoded
        var msg_type := str(msg.get("type", ""))
        if msg_type == "RUN_START":
            _handle_run_start(msg, udp.get_packet_ip(), udp.get_packet_port())


func _handle_run_start(msg: Dictionary, sender_ip: String, sender_port: int) -> void:
    peer_ip = sender_ip
    peer_port = sender_port

    run_payload = msg.get("payload", {})
    run_id = str(msg.get("run_id", run_payload.get("bids_stem", run_id)))

    if msg.has("condition_row") and typeof(msg["condition_row"]) == TYPE_DICTIONARY:
        run_condition = msg["condition_row"]
    elif run_payload.has("condition_row") and typeof(run_payload["condition_row"]) == TYPE_DICTIONARY:
        run_condition = run_payload["condition_row"]
    else:
        run_condition = {}

    var seed := int(msg.get("seed", run_payload.get("seed", 1)))
    rng.seed = seed
    output_dir = str(msg.get("output_dir", output_dir))

    _apply_condition(run_condition)
    _reset_run_state()
    running = true

    _send("SYNC", {"marker": "arena_ready", "run_id": run_id})
    _start_trial(0)


func _active_trial() -> Dictionary:
    if trial_index < 0 or trial_index >= trial_plan.size():
        return {}
    if typeof(trial_plan[trial_index]) != TYPE_DICTIONARY:
        return {}
    return trial_plan[trial_index]


func _start_trial(index: int) -> void:
    if index >= trial_plan.size():
        _finish_run("ok")
        return

    trial_index = index
    trial_elapsed_s = 0.0
    var trial := _active_trial()

    var trial_num_gems := int(trial.get("num_gems", default_num_gems))
    var trial_show_gems := bool(trial.get("show_gems", default_show_gems))
    var reset_gems := bool(trial.get("reset_gems", index == 0))
    if reset_gems or gems.size() != trial_num_gems:
        _spawn_gems(trial_num_gems, trial_show_gems)
    else:
        _set_gem_visibility(trial_show_gems)

    _send(
        "EVENT",
        {
            "event_type": "phase_started",
            "phase": str(trial.get("name", "trial_%02d" % index)),
            "mode": str(trial.get("mode", "search")),
            "trial_nr": index,
            "trial_duration_s": float(trial.get("duration_s", 0.0)),
            "show_gems": trial_show_gems,
            "num_gems": trial_num_gems,
            "run_id": run_id,
        }
    )


func _send(msg_type: String, payload: Dictionary) -> void:
    if peer_ip == "" or peer_port <= 0:
        return
    var packet := {
        "type": msg_type,
        "timestamp_ns": int(Time.get_ticks_usec() * 1000),
        "payload": payload,
    }
    udp.set_dest_address(peer_ip, peer_port)
    udp.put_packet(JSON.stringify(packet).to_utf8_buffer())


func _update_navigation(delta: float) -> void:
    var input_vec := Vector2.ZERO
    if Input.is_key_pressed(KEY_W):
        input_vec.y -= 1.0
    if Input.is_key_pressed(KEY_S):
        input_vec.y += 1.0
    if Input.is_key_pressed(KEY_A):
        input_vec.x -= 1.0
    if Input.is_key_pressed(KEY_D):
        input_vec.x += 1.0
    if input_vec.length() > 1.0:
        input_vec = input_vec.normalized()

    if Input.is_key_pressed(KEY_Q):
        player_yaw -= turn_speed * delta
    if Input.is_key_pressed(KEY_E):
        player_yaw += turn_speed * delta

    var forward := Vector3(sin(player_yaw), 0.0, cos(player_yaw))
    var right := Vector3(forward.z, 0.0, -forward.x)
    var horizontal_move := (forward * -input_vec.y + right * input_vec.x) * player_speed * delta
    player_speed_m_s = horizontal_move.length() / max(delta, 1e-6)
    player_pos += horizontal_move

    var p2 := Vector2(player_pos.x, player_pos.z)
    var max_radius := arena_radius - 0.45
    if p2.length() > max_radius:
        p2 = p2.normalized() * max_radius
        player_pos.x = p2.x
        player_pos.z = p2.y

    if camera != null:
        camera.position = player_pos
        camera.rotation = Vector3(0.0, player_yaw, 0.0)


func _collect_gems() -> void:
    var player_planar := Vector2(player_pos.x, player_pos.z)
    var trial := _active_trial()
    var phase_name := str(trial.get("name", "navigation"))

    for idx in range(gems.size()):
        var gem: Dictionary = gems[idx]
        if bool(gem.get("found", false)):
            continue
        var loc2: Vector2 = gem["position"]
        if player_planar.distance_to(loc2) <= collection_radius:
            gem["found"] = true
            gems[idx] = gem
            score += float(gem.get("reward", 0))
            var marker: MeshInstance3D = gem.get("marker")
            if marker != null:
                marker.visible = false

            var event_payload := {
                "event_type": "gem_collected",
                "phase": phase_name,
                "trial_nr": trial_index,
                "gem_id": int(gem.get("id", idx)),
                "reward": int(gem.get("reward", 0)),
                "score": score,
                "x": loc2.x,
                "z": loc2.y,
                "trial_time_s": trial_elapsed_s,
                "run_time_s": phase_elapsed_s,
            }
            gem_events.append(event_payload)
            _send("EVENT", event_payload)


func _record_frame() -> void:
    var timestamp_ns := int(Time.get_ticks_usec() * 1000)
    var trial := _active_trial()
    var phase_name := str(trial.get("name", "navigation"))
    var mode_name := str(trial.get("mode", "search"))

    frame_trace.append(
        {
            "timestamp_ns": timestamp_ns,
            "trial_nr": trial_index,
            "phase": phase_name,
            "mode": mode_name,
            "trial_time_s": trial_elapsed_s,
            "run_time_s": phase_elapsed_s,
            "x": player_pos.x,
            "y": player_pos.y,
            "z": player_pos.z,
            "yaw_rad": player_yaw,
            "speed_m_s": player_speed_m_s,
            "score": score,
        }
    )

    if phase_elapsed_s >= next_sync_s:
        next_sync_s += 1.0
        _send(
            "SYNC",
            {
                "marker": "pose",
                "trial_nr": trial_index,
                "phase": phase_name,
                "trial_time_s": trial_elapsed_s,
                "run_time_s": phase_elapsed_s,
                "x": player_pos.x,
                "z": player_pos.z,
                "yaw_rad": player_yaw,
                "score": score,
            }
        )


func _finish_run(status: String) -> void:
    if not running:
        return
    running = false

    var trace_path := _write_trace_jsonl()
    _write_meta_json()

    var n_found := 0
    for gem in gems:
        if bool(gem.get("found", false)):
            n_found += 1

    _send(
        "RUN_ENDED",
        {
            "status": status,
            "run_id": run_id,
            "world_trace_jsonl": trace_path,
            "score": score,
            "gems_total": gems.size(),
            "gems_found": n_found,
            "duration_s": phase_elapsed_s,
            "n_trials": trial_plan.size(),
            "last_trial_index": trial_index,
        }
    )

    if auto_quit:
        get_tree().quit()


func _write_trace_jsonl() -> String:
    DirAccess.make_dir_recursive_absolute(output_dir)
    var trace_path := output_dir.path_join("%s_world_trace.jsonl" % run_id)
    var f := FileAccess.open(trace_path, FileAccess.WRITE)
    if f == null:
        return ""
    for row in frame_trace:
        f.store_line(JSON.stringify(row))
    f.close()
    return trace_path


func _write_meta_json() -> void:
    DirAccess.make_dir_recursive_absolute(output_dir)
    var meta_path := output_dir.path_join("%s_world_meta.json" % run_id)
    var gem_rows: Array = []
    for gem in gems:
        var loc2: Vector2 = gem["position"]
        gem_rows.append(
            {
                "id": int(gem.get("id", -1)),
                "x": loc2.x,
                "z": loc2.y,
                "reward": int(gem.get("reward", 0)),
                "found": bool(gem.get("found", false)),
            }
        )
    var payload := {
        "run_id": run_id,
        "condition_row": run_condition,
        "trial_plan": trial_plan,
        "score": score,
        "duration_s": phase_elapsed_s,
        "gems": gem_rows,
        "gem_events": gem_events,
    }
    var f := FileAccess.open(meta_path, FileAccess.WRITE)
    if f == null:
        return
    f.store_string(JSON.stringify(payload, "\t"))
    f.close()


func _new_material(color: Color, roughness: float, metallic: float, alpha_blend: bool = false) -> StandardMaterial3D:
    var mat := StandardMaterial3D.new()
    mat.albedo_color = color
    mat.roughness = roughness
    mat.metallic = metallic
    if alpha_blend:
        mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
        mat.cull_mode = BaseMaterial3D.CULL_DISABLED
    return mat
