# =====================================================================
#  Air Control Sensors — 3D-сцена, версия 2 (Blender 4.x)
#
#  Что в сцене:
#    • устройство на столе: экран (AQI, статус, CO2, температура,
#      влажность), световой индикатор цвета воздуха, решётка,
#      прорези сбоку, USB-C, логотип;
#    • телефон с приложением Air Control Sensors того же цвета
#      и советами для 4 групп;
#    • комната: стол, стена, свет из окна.
#
#  Как запустить:
#    1. Blender 4.0+ → вкладка "Scripting" → "New".
#    2. Вставить скрипт → ▶ Run Script (Alt+P).
#    3. F12 — рендер. Сохранить: Image → Save As.
#
#  ВНИМАНИЕ: скрипт удаляет всё в сцене и строит заново.
# =====================================================================

import math

import bmesh
import bpy
from mathutils import Vector

# ---------------------------------------------------------------------
#  НАСТРОЙКИ — меняйте здесь
# ---------------------------------------------------------------------

# "home"   — устройство + телефон с приложением на столе
# "lineup" — 4 устройства в ряд: зелёный, жёлтый, оранжевый, красный
SCENE_MODE = "home"

# Уровень воздуха для режима "home": "green", "yellow", "orange", "red"
AIR_STATE = "yellow"

AIR_STATES = {
    #           цвет        AQI    статус на экране
    "green":  ("#5CC28A", "35",  "GOOD"),
    "yellow": ("#F2C14E", "78",  "MODERATE"),
    "orange": ("#F2994A", "125", "SENSITIVE"),
    "red":    ("#E5574F", "180", "UNHEALTHY"),
}

# Данные комнаты на экране устройства
ROOM_CO2 = "CO2 650"
ROOM_TEMP = "22.5°C"
ROOM_HUM = "38%"

# Данные на экране телефона (улица)
PHONE_CITY = "Almaty"
PHONE_WEATHER = ("-6°C", "72%", "1.8 m/s")
PHONE_ADVICE = {
    #           советы для групп в каждом состоянии воздуха
    "green":  ("Adults: enjoy a walk", "Kids: play outside", "Asthma: all good", "Sport: run outside"),
    "yellow": ("Adults: OK to walk", "Kids: max 1 hour", "Asthma: stay inside", "Sport: train indoors"),
    "orange": ("Adults: short walks", "Kids: stay inside", "Asthma: stay inside", "Sport: train indoors"),
    "red":    ("Adults: wear a mask", "Kids: stay inside", "Asthma: stay inside", "Sport: rest today"),
}

BODY_COLOR = "#E6E6E3"
SCREEN_COLOR = "#14181C"
SCREEN_TEXT = "#F1EFE8"
WALL_COLOR = "#EDEAE4"
DESK_COLOR = "#B98C62"

# Размеры устройства в метрах (1 см = 0.01)
BODY_W, BODY_D, BODY_H = 0.08, 0.03, 0.12

RESOLUTION = (1920, 1080)

# ---------------------------------------------------------------------
#  Служебные функции
# ---------------------------------------------------------------------

ERRORS = []
DONE = []
STATE = {}
MATS = {}


def step(name, func, *args):
    """Один шаг сцены. Ошибка в шаге не ломает остальные шаги."""
    try:
        func(*args)
        DONE.append(name)
        print("[OK] " + name)
    except Exception as exc:  # noqa: BLE001
        ERRORS.append(name + ": " + str(exc))
        print("[ERROR] " + name + ": " + str(exc))


def hex_to_linear(hex_color, alpha=1.0):
    hex_color = hex_color.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(hex_color[i:i + 2], 16) / 255.0
        c = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        out.append(c)
    return (out[0], out[1], out[2], alpha)


def set_input(node, names, value):
    for name in names:
        if name in node.inputs:
            node.inputs[name].default_value = value
            return True
    return False


def material(name, hex_color, roughness=0.5, metallic=0.0,
             emission_hex=None, emission_strength=0.0):
    """Создаёт материал один раз и потом берёт готовый."""
    if name in MATS:
        return MATS[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    color = hex_to_linear(hex_color)
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        set_input(bsdf, ["Base Color"], color)
        set_input(bsdf, ["Roughness"], roughness)
        set_input(bsdf, ["Metallic"], metallic)
        if emission_hex:
            set_input(bsdf, ["Emission Color", "Emission"], hex_to_linear(emission_hex))
            set_input(bsdf, ["Emission Strength"], emission_strength)
    MATS[name] = mat
    return mat


def get_collection(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def _place(obj, collection, location, parent):
    collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent  # координаты дальше — относительно родителя
    obj.location = location
    return obj


def box(name, size, location, mat, collection, parent=None, bevel=0.0):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    bm.to_mesh(mesh)
    bm.free()
    obj = _place(bpy.data.objects.new(name, mesh), collection, location, parent)
    if mat is not None:
        mesh.materials.append(mat)
    if bevel > 0:
        mod = obj.modifiers.new("Rounded", "BEVEL")
        mod.width = bevel
        mod.segments = 6
        mod.limit_method = "ANGLE"
    return obj


def disc(name, radius, depth, location, mat, collection, parent=None):
    """Плоский цилиндр лицом к камере (ось -Y)."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=64,
                          radius1=radius, radius2=radius, depth=depth)
    bm.to_mesh(mesh)
    bm.free()
    obj = _place(bpy.data.objects.new(name, mesh), collection, location, parent)
    obj.rotation_euler = (math.radians(90), 0.0, 0.0)
    if mat is not None:
        mesh.materials.append(mat)
    return obj


def text(name, body, size, location, mat, collection, parent=None,
         align="CENTER", extrude=0.0002):
    """Текст лицом к камере. align: LEFT / CENTER / RIGHT."""
    curve = bpy.data.curves.new(name, type="FONT")
    curve.body = body
    curve.size = size
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.extrude = extrude
    obj = _place(bpy.data.objects.new(name, curve), collection, location, parent)
    obj.rotation_euler = (math.radians(90), 0.0, 0.0)
    if mat is not None:
        curve.materials.append(mat)
    return obj


def empty(name, location, collection, rotation=(0.0, 0.0, 0.0)):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = 0.02
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    return obj


def look_at(obj, target):
    direction = Vector(target) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def state_info(state):
    return AIR_STATES.get(state, AIR_STATES["yellow"])


def state_material(state):
    """Материал цвета воздуха. Яркость умеренная, чтобы цвет не выгорал в белый."""
    color, _, _ = state_info(state)
    return material("ACS_State_" + state, color, roughness=0.35,
                    emission_hex=color, emission_strength=1.2)


# ---------------------------------------------------------------------
#  Сцена
# ---------------------------------------------------------------------

def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        if coll.name.startswith("ACS_"):
            bpy.data.collections.remove(coll)
    for data in (bpy.data.meshes, bpy.data.materials, bpy.data.curves,
                 bpy.data.lights, bpy.data.cameras):
        for block in list(data):
            if block.users == 0:
                data.remove(block)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "CENTIMETERS"


def build_room():
    coll = get_collection("ACS_Room")
    STATE["room"] = coll
    # Стол: верх стола на высоте z = 0
    box("ACS_Desk", (1.4, 0.7, 0.03), (0.0, 0.12, -0.015),
        material("ACS_Desk", DESK_COLOR, roughness=0.55), coll, bevel=0.004)
    # Стена за столом
    box("ACS_Wall", (3.0, 0.02, 2.0), (0.0, 0.48, 0.6),
        material("ACS_Wall", WALL_COLOR, roughness=0.85), coll)


def build_device(prefix, location, state):
    """Одно устройство. location — точка на столе под центром устройства."""
    color, aqi, status = state_info(state)
    coll = get_collection(prefix)
    cutters = get_collection(prefix + "_Cutters")

    root = empty(prefix + "_Root", (location[0], location[1], location[2] + 0.066), coll)
    front = -BODY_D / 2

    m_body = material("ACS_Body", BODY_COLOR, roughness=0.55)
    m_screen = material("ACS_Screen", SCREEN_COLOR, roughness=0.12)
    m_stext = material("ACS_ScreenText", SCREEN_TEXT, roughness=0.4,
                       emission_hex=SCREEN_TEXT, emission_strength=1.5)
    m_dim = material("ACS_ScreenDim", "#8C9196", roughness=0.4,
                     emission_hex="#8C9196", emission_strength=0.8)
    m_ring = material("ACS_Ring", "#8A8C8E", roughness=0.35, metallic=0.6)
    m_logo = material("ACS_Logo", "#9A9C9E", roughness=0.5)
    m_state = state_material(state)

    # Корпус и подставка
    body = box(prefix + "_Body", (BODY_W, BODY_D, BODY_H), (0.0, 0.0, 0.0),
               m_body, coll, root, bevel=0.006)
    box(prefix + "_Base", (0.07, 0.04, 0.006), (0.0, 0.0, -0.063),
        m_body, coll, root, bevel=0.002)

    # Прорези: решётка спереди, прорези сбоку, USB-C сбоку
    vent = box(prefix + "_Cut_Front", (0.05, 0.012, 0.002), (0.0, front, -0.035),
               None, cutters, root)
    arr = vent.modifiers.new("Array", "ARRAY")
    arr.count = 3
    arr.use_relative_offset = True
    arr.relative_offset_displace = (0.0, 0.0, -2.0)

    side = box(prefix + "_Cut_Side", (0.012, 0.016, 0.0018), (BODY_W / 2, 0.0, 0.022),
               None, cutters, root)
    arr2 = side.modifiers.new("Array", "ARRAY")
    arr2.count = 4
    arr2.use_relative_offset = True
    arr2.relative_offset_displace = (0.0, 0.0, -2.5)

    box(prefix + "_Cut_USBC", (0.012, 0.009, 0.0035), (BODY_W / 2, 0.0, -0.045),
        None, cutters, root)

    for obj in cutters.objects:
        obj.display_type = "WIRE"
        obj.hide_render = True
    cut = body.modifiers.new("Cut slots", "BOOLEAN")
    cut.operation = "DIFFERENCE"
    cut.operand_type = "COLLECTION"
    cut.collection = cutters
    cut.solver = "EXACT"
    for obj in cutters.objects:
        try:
            obj.hide_set(True)
        except Exception:  # noqa: BLE001
            pass

    # Экран: AQI, статус, данные комнаты
    sz = 0.026  # центр экрана по высоте
    box(prefix + "_Screen", (0.064, 0.002, 0.050), (0.0, front - 0.0005, sz),
        m_screen, coll, root)
    ty = front - 0.0018  # слой текста перед экраном
    text(prefix + "_T_Label", "AQI", 0.0045, (-0.028, ty, sz + 0.019), m_dim, coll, root, "LEFT")
    text(prefix + "_T_AQI", aqi, 0.018, (-0.028, ty, sz + 0.004), m_stext, coll, root, "LEFT")
    text(prefix + "_T_Status", status, 0.0045, (0.028, ty, sz + 0.019), m_state, coll, root, "RIGHT")
    box(prefix + "_StatusBar", (0.022, 0.0002, 0.0015), (0.017, front - 0.0017, sz + 0.0135),
        m_state, coll, root)
    box(prefix + "_Divider", (0.056, 0.0002, 0.0004), (0.0, front - 0.0017, sz - 0.008),
        m_dim, coll, root)
    text(prefix + "_T_CO2", ROOM_CO2, 0.0040, (-0.021, ty, sz - 0.017), m_stext, coll, root)
    text(prefix + "_T_Temp", ROOM_TEMP, 0.0040, (0.0, ty, sz - 0.017), m_stext, coll, root)
    text(prefix + "_T_Hum", ROOM_HUM, 0.0040, (0.021, ty, sz - 0.017), m_stext, coll, root)

    # Световой индикатор цвета воздуха
    led_z = -0.016
    disc(prefix + "_LED_Ring", 0.0125, 0.0012, (0.0, front - 0.0004, led_z), m_ring, coll, root)
    disc(prefix + "_LED", 0.0100, 0.0020, (0.0, front - 0.0008, led_z), m_state, coll, root)
    glow_data = bpy.data.lights.new(prefix + "_Glow", type="POINT")
    glow_data.color = hex_to_linear(color)[:3]
    glow_data.energy = 0.15
    glow_data.shadow_soft_size = 0.01
    glow = bpy.data.objects.new(prefix + "_Glow", glow_data)
    _place(glow, coll, (0.0, front - 0.012, led_z), root)

    # Логотип под решёткой
    text(prefix + "_Logo", "AIR CONTROL SENSORS", 0.0042, (0.0, front - 0.0002, -0.050),
         m_logo, coll, root)

    STATE.setdefault("bodies", []).append(body)
    return root


def build_phone(location, state):
    """Телефон на подставке с экраном приложения."""
    color, aqi, status = state_info(state)
    coll = get_collection("ACS_Phone")
    tilt = math.radians(-15)  # наклон назад
    root = empty("ACS_Phone_Root", location, coll, rotation=(tilt, 0.0, 0.0))

    m_phone = material("ACS_PhoneBody", "#1C1E21", roughness=0.3, metallic=0.4)
    m_app = material("ACS_AppBg", "#F6F7F8", roughness=0.3,
                     emission_hex="#F6F7F8", emission_strength=0.6)
    m_card = material("ACS_AppCard", "#E4E8EB", roughness=0.4,
                      emission_hex="#E4E8EB", emission_strength=0.5)
    m_ink = material("ACS_AppInk", "#13232C", roughness=0.5)
    m_soft = material("ACS_AppSoft", "#6A7880", roughness=0.5)
    m_state = state_material(state)
    m_stand = material("ACS_Stand", "#3A3D40", roughness=0.6)

    box("ACS_Phone", (0.072, 0.008, 0.150), (0.0, 0.0, 0.0), m_phone, coll, root, bevel=0.0035)
    box("ACS_PhoneStand", (0.045, 0.030, 0.070), (0.0, 0.020, -0.040), m_stand, coll, root, bevel=0.003)

    sy = -0.0041   # экран
    cy = -0.0044   # карточки
    ty = -0.0047   # текст
    box("ACS_AppScreen", (0.066, 0.0004, 0.140), (0.0, sy, 0.0), m_app, coll, root)

    text("ACS_App_Title", "Air Control Sensors", 0.0055, (-0.029, ty, 0.060), m_ink, coll, root, "LEFT", 0.0001)
    text("ACS_App_City", PHONE_CITY, 0.0040, (-0.029, ty, 0.052), m_soft, coll, root, "LEFT", 0.0001)

    # Большая карточка AQI цвета воздуха
    box("ACS_App_AQICard", (0.058, 0.0003, 0.032), (0.0, cy, 0.029), m_state, coll, root)
    text("ACS_App_AQI", aqi, 0.016, (0.0, ty, 0.033), m_ink, coll, root, "CENTER", 0.0001)
    text("ACS_App_Status", status, 0.0045, (0.0, ty, 0.019), m_ink, coll, root, "CENTER", 0.0001)

    # Погода: три карточки
    for i, (x, value) in enumerate(zip((-0.020, 0.0, 0.020), PHONE_WEATHER)):
        box("ACS_App_W%d" % i, (0.018, 0.0003, 0.014), (x, cy, -0.002), m_card, coll, root)
        text("ACS_App_WT%d" % i, value, 0.0035, (x, ty, -0.002), m_ink, coll, root, "CENTER", 0.0001)

    # Советы для 4 групп
    advice = PHONE_ADVICE.get(state, PHONE_ADVICE["yellow"])
    for i, line in enumerate(advice):
        z = -0.020 - i * 0.011
        box("ACS_App_Row%d" % i, (0.058, 0.0003, 0.009), (0.0, cy, z), m_card, coll, root)
        disc("ACS_App_Dot%d" % i, 0.0015, 0.0002, (-0.024, ty, z), m_state, coll, root)
        text("ACS_App_Adv%d" % i, line, 0.0035, (-0.020, ty, z), m_ink, coll, root, "LEFT", 0.0001)


def build_lights():
    coll = get_collection("ACS_Lights")
    target = (0.0, 0.0, 0.06)

    key = bpy.data.lights.new("ACS_Window_Light", type="AREA")
    key.energy = 120.0
    key.size = 1.0
    key.color = (1.0, 0.97, 0.92)
    key_obj = bpy.data.objects.new("ACS_Window_Light", key)
    coll.objects.link(key_obj)
    key_obj.location = (-0.8, -0.3, 0.6)
    look_at(key_obj, target)

    fill = bpy.data.lights.new("ACS_Fill_Light", type="AREA")
    fill.energy = 25.0
    fill.size = 1.2
    fill_obj = bpy.data.objects.new("ACS_Fill_Light", fill)
    coll.objects.link(fill_obj)
    fill_obj.location = (0.7, -0.7, 0.3)
    look_at(fill_obj, target)

    scene = bpy.context.scene
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("ACS_World")
        scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = hex_to_linear("#DDE3E8")
        bg.inputs[1].default_value = 0.4


def build_camera(location, target, lens, focus):
    coll = get_collection("ACS_Lights")
    cam_data = bpy.data.cameras.new("ACS_Camera")
    cam_data.lens = lens
    cam_data.clip_start = 0.01
    cam_data.clip_end = 50
    cam = bpy.data.objects.new("ACS_Camera", cam_data)
    coll.objects.link(cam)
    cam.location = location
    look_at(cam, target)
    bpy.context.scene.camera = cam
    try:
        cam_data.dof.use_dof = True
        cam_data.dof.focus_object = focus
        cam_data.dof.aperture_fstop = 8.0
    except Exception:  # noqa: BLE001
        pass


def setup_render():
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except Exception:  # noqa: BLE001
            continue
    scene.render.resolution_x = RESOLUTION[0]
    scene.render.resolution_y = RESOLUTION[1]
    scene.render.resolution_percentage = 100
    scene.render.filepath = "//air_control_" + SCENE_MODE
    try:
        scene.eevee.use_bloom = True  # есть только в 4.0–4.1
        scene.eevee.bloom_intensity = 0.03
    except Exception:  # noqa: BLE001
        pass
    for view in ("AgX", "Filmic"):
        try:
            scene.view_settings.view_transform = view
            break
        except Exception:  # noqa: BLE001
            continue


def setup_viewport():
    screen = bpy.context.screen
    if screen is None:
        return
    for area in screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = "MATERIAL"
                    space.region_3d.view_perspective = "CAMERA"


def show_report():
    print("----- Air Control Sensors v2 -----")
    print("Steps done: " + str(len(DONE)) + ", errors: " + str(len(ERRORS)))
    for err in ERRORS:
        print("  " + err)

    def draw(self, _context):
        if ERRORS:
            self.layout.label(text="Ошибок: " + str(len(ERRORS)))
            for err in ERRORS:
                self.layout.label(text=err[:120])
        else:
            self.layout.label(text="Готово! Нажмите F12 для рендера.")

    try:
        bpy.context.window_manager.popup_menu(
            draw, title="Air Control Sensors",
            icon="ERROR" if ERRORS else "CHECKMARK")
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------
#  Запуск
# ---------------------------------------------------------------------

step("Clear scene", clear_scene)
step("Room", build_room)

if SCENE_MODE == "lineup":
    for i, st in enumerate(("green", "yellow", "orange", "red")):
        step("Device " + st, build_device, "ACS_Device_" + st, (-0.165 + i * 0.11, 0.0, 0.0), st)
    step("Lights", build_lights)
    step("Camera", lambda: build_camera((0.0, -0.72, 0.18), (0.0, 0.0, 0.062), 50,
                                         STATE["bodies"][1] if len(STATE.get("bodies", [])) > 1 else None))
else:
    step("Device", build_device, "ACS_Device", (-0.06, 0.0, 0.0), AIR_STATE)
    step("Phone with app", build_phone, (0.075, -0.005, 0.0745), AIR_STATE)
    step("Lights", build_lights)
    step("Camera", lambda: build_camera((0.06, -0.46, 0.17), (0.01, 0.0, 0.066), 50,
                                         STATE["bodies"][0] if STATE.get("bodies") else None))

step("Render settings", setup_render)
step("Viewport", setup_viewport)
show_report()
