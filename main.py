import os, random, curses, time
gold = 0

def is_walkable(terrain, map_name, x, y):
    """Check if a tile is walkable (not blocked by collision or locked doors)."""
    if x < 0 or y < 0 or y >= len(terrain) or x >= len(terrain[y]):
        return False
    tile = terrain[y][x]
    # Blocked tiles: forest (#), water (~), walls (%), and enemies
    if tile in ['#', '~', '%'] or tile in ENEMY_TILES:
        return False
    if tile == '|':
        return (map_name, x, y) in UNLOCKED_DOORS or (map_name, x, y) in LOCKS and LOCKS[(map_name, x, y)] in inventory_global
    return True

def load_map_from_string(map_string):
    """Load a map from a multi-line string"""
    lines = map_string.strip().split('\n')
    terrain = []
    for line in lines:
        terrain.append(list(line.rstrip()))  # Remove trailing whitespace from each line
    return terrain

def load_map_from_file(filename):
    """Load a map from a text file"""
    try:
        with open(filename, 'r') as f:
            return load_map_from_string(f.read())
    except FileNotFoundError:
        print(f"Map file '{filename}' not found!")
        return None

def safe_pad_refresh(pad, pad_top, pad_left, screen_top, screen_left, screen_bottom, screen_right, max_y, max_x, map_height, map_width):
    """Refresh a pad using safe bounds based on screen and map dimensions."""
    bottom = min(screen_bottom, max_y - 1, map_height - 1)
    right = min(screen_right, max_x - 1, map_width - 1)
    if bottom < screen_top or right < screen_left:
        return
    try:
        pad.refresh(pad_top, pad_left, screen_top, screen_left, bottom, right)
    except curses.error:
        pass

def draw_inventory_sidebar(stdscr, inventory, inv_x, inv_width, top_row, bottom_row):
    """Draw a fixed inventory sidebar on the right side of the screen."""
    if inv_x < 0 or inv_width < 6 or bottom_row <= top_row + 2:
        return
    inner_width = inv_width - 2
    try:
        stdscr.addstr(top_row, inv_x, "+" + "-" * inner_width + "+")
        stdscr.addstr(top_row + 1, inv_x, "|" + " INVENTORY".ljust(inner_width)[:inner_width] + "|")
        stdscr.addstr(top_row + 2, inv_x, "+" + "-" * inner_width + "+")

        for y in range(top_row + 3, bottom_row):
            item_idx = y - (top_row + 3)
            item_text = inventory[item_idx] if item_idx < len(inventory) else ""
            stdscr.addstr(y, inv_x, "|" + item_text.ljust(inner_width)[:inner_width] + "|")

        stdscr.addstr(bottom_row, inv_x, "+" + "-" * inner_width + "+")
    except curses.error:
        pass

def draw_status_bar(stdscr, health, playerAttack, playerDefence, gold, max_x):
    """Draw the top status bar with player stats."""
    status = f"Health: {health}   Attack: {playerAttack}   Defence: {playerDefence}   Gold: {gold}"
    try:
        stdscr.addstr(0, 0, status.ljust(max_x)[:max_x])
    except curses.error:
        pass

def get_tile_color(tile, has_color):
    """Return the color pair for a tile"""
    if not has_color:
        return 0
    
    if tile == '#':
        return curses.color_pair(2)  # Green for forest
    elif tile == '~':
        return curses.color_pair(3)  # Blue for water
    elif tile == '%':
        return curses.color_pair(4)  # Red for walls
    elif tile == 'X':
        return curses.color_pair(5)  # Yellow for doors
    elif tile == '=':
        return curses.color_pair(6)  # Yellow for chests
    elif tile == ',':
        return curses.color_pair(7) | curses.A_DIM  # Road (light brown/limestone)
    elif tile in ENEMY_TILES:
        return curses.color_pair(8) | curses.A_BOLD  # Red for enemies
    else:
        return curses.color_pair(1)  # White for grass


def find_spawn_point(terrain):
    """Find a spawn point tile ('_') and replace it with floor."""
    for y, row in enumerate(terrain):
        for x, tile in enumerate(row):
            if tile == '_':
                terrain[y][x] = '.'
                return x, y
    return None

# Map definitions - load from external files
MAP_FILES = {
    "forest": "forest.txt",
    "caves": "caves.txt",
}

def load_maps():
    """Load all maps from their files."""
    maps = {}
    for map_name, filename in MAP_FILES.items():
        terrain = load_map_from_file(filename)
        if terrain:
            maps[map_name] = terrain
        else:
            print(f"Failed to load map '{map_name}' from '{filename}'")
    return maps

def scan_surrounding_tiles(terrain, x, y, radius=1, include_center=False):
    """Return a list of surrounding ASCII tiles around (x, y).

    Each entry includes the tile character, absolute coordinates, and relative offset.
    This is useful for enemy detection, locked door checks, and other nearby tile logic.
    """
    results = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0 and not include_center:
                continue
            tx = x + dx
            ty = y + dy
            if ty < 0 or ty >= len(terrain) or tx < 0 or tx >= len(terrain[ty]):
                continue
            tile = terrain[ty][tx]
            if tile and tile != '.' and tile != ' ':
                results.append({
                    "x": tx,
                    "y": ty,
                    "dx": dx,
                    "dy": dy,
                    "tile": tile,
                })
    return results

UNLOCKED_DOORS = set()

def is_locked_door(map_name, x, y):
    return (map_name, x, y) in LOCKS

def can_unlock_door(map_name, x, y, inventory_items):
    required = LOCKS.get((map_name, x, y))
    return required is not None and required in inventory_items

def unlock_door(map_name, x, y, inventory_items):
    required = LOCKS.get((map_name, x, y))
    if required and required in inventory_items:
        inventory_items.remove(required)
        UNLOCKED_DOORS.add((map_name, x, y))
        return True, required
    return False, None


def pickup_chest(map_name, x, y, terrain, inventory_items):
    """Pick up a chest at the player's current location."""
    chest_key = (map_name, x, y)
    if chest_key in CHESTS and chest_key not in COLLECTED_CHESTS and terrain[y][x] == '=':
        loot = CHESTS[chest_key]
        inventory_items.append(loot)
        COLLECTED_CHESTS.add(chest_key)
        terrain[y][x] = '.'
        return loot
    return None


def adjacent_locked_door_message(map_name, terrain, x, y, inventory_items):
    """Return a message when the player is next to a locked door."""
    for tile_info in scan_surrounding_tiles(terrain, x, y, radius=1):
        if tile_info["tile"] == '|':
            lock_pos = (map_name, tile_info["x"], tile_info["y"])
            if lock_pos in UNLOCKED_DOORS:
                return "There is an unlocked door nearby."
            required = LOCKS.get(lock_pos)
            if required is None:
                continue
            if required in inventory_items:
                return f"You can unlock this door with {required}."
            return f"You need {required} to open the door."
    return None

#######################################################################################################
# Door definitions: (map_name, x, y) -> (destination_map, spawn_x, spawn_y)
# Each door position maps to its destination
DOORS = {
    ("forest", 26, 1): ("caves", 26, 1),          # Forest door -> caves entrance at top
    ("forest", 2, 9): ("caves", 2, 9),            # Cliff door top -> caves entrance top left
    ("forest", 1, 16): ("caves", 1, 16),          # Cliff door bottom -> caves entrance bottom left
    ("forest", 29, 16): ("caves", 29, 16),        # Island door -> caves exit bottom right
    ("caves", 26, 1): ("forest", 26, 1),          # Caves exit top -> forest door
    ("caves", 2, 9): ("forest", 2, 9),            # Caves entrance top left -> forest cliff door
    ("caves", 1, 16): ("forest", 1, 16),          # Caves entrance bottom left -> forest cliff door
    ("caves", 29, 16): ("forest", 29, 16),        # Caves exit bottom right -> forest island door
}

CHESTS = {
    ("forest", 24, 15): "Legendary Longsword", #chest in the island in the forest map
    ("forest", 40, 11): "Padded Armour", #chest in the forest
    ("caves", 13, 7): "Health Potion", #chest in the caves)
}

LOCKS = {
    ("caves", 15, 16): "Rusted Key", #locked door that leads to the lake island containing the legendary longsword)
    ("forest", 1, 4): "Bandit Key", #locked door that leads to victory area
    ("forest", 1, 5): "Bandit Key",  #locked door that leads to victory area
}

ENEMIES = {
    "goblin": {
        "tile": "£",
        "health": 20,
        "damage": 6,
        "defence": 1,
    },
    "bandit": {
        "tile": "&",
        "health": 30,
        "damage": 12,
        "defence": 2,
    },
    "rat": {
        "tile": "^",
        "health": 4,
        "damage": 5,
        "defence": 0,
    },
}

PEOPLE = {
    ("forest", 6, 3,): "This place has become very dangerous since the goblins moved in. Be careful out there!", #old man next to start location
    ("forest", 1, 6,): "Nobody gets in or out of the valley, orders of the Bandit King!", #bandit guarding locked door to victory area
    ("forest", 7, 17,): "They say there's a legendary sword in that little island over there" #hint to the legendary longsword chest in the island in the forest map
}

ENEMY_TILES = {v["tile"]: k for k, v in ENEMIES.items()}

def calculate_damage(attack, defence):
    """Return damage after subtracting defence, with a minimum of zero."""
    return max(0, attack - defence)


def apply_combat(attacker, defender):
    """Apply attacker damage to defender health and return actual damage dealt."""
    damage = calculate_damage(attacker.get("damage", 0), defender.get("defence", 0))
    defender["health"] = max(0, defender.get("health", 0) - damage)
    return damage


def is_enemy_tile(tile):
    return tile in ENEMY_TILES


def initialize_enemies(terrain):
    """Scan the terrain for enemy tiles and initialize their current state."""
    active = {}
    for y, row in enumerate(terrain):
        for x, tile in enumerate(row):
            if tile in ENEMY_TILES:
                enemy_type = ENEMY_TILES[tile]
                enemy_info = ENEMIES[enemy_type]
                active[(x, y)] = {
                    "type": enemy_type,
                    "tile": tile,
                    "health": enemy_info["health"],
                    "damage": enemy_info["damage"],
                    "defence": enemy_info["defence"],
                }
    return active


def process_adjacent_enemy_combat(terrain, player_x, player_y, active_enemies, playerAttack, playerDefence, health):
    """Apply automatic combat when enemies are adjacent to the player."""
    messages = []
    defeated_positions = []

    for tile_info in scan_surrounding_tiles(terrain, player_x, player_y, radius=1):
        if not is_enemy_tile(tile_info["tile"]):
            continue

        enemy_pos = (tile_info["x"], tile_info["y"])
        enemy_state = active_enemies.get(enemy_pos)
        if enemy_state is None:
            continue

        damage_to_enemy = apply_combat({"damage": playerAttack}, enemy_state)
        if damage_to_enemy > 0:
            messages.append(f"You hit the {enemy_state['type']} for {damage_to_enemy}.")

        if enemy_state["health"] > 0:
            damage_to_player = calculate_damage(enemy_state["damage"], playerDefence)
            if damage_to_player > 0:
                health = max(0, health - damage_to_player)
                messages.append(f"{enemy_state['type'].title()} hits you for {damage_to_player}.")
            else:
                messages.append(f"{enemy_state['type'].title()} attacks but you block it.")

        if enemy_state["health"] <= 0:
            messages.append(f"You defeated the {enemy_state['type']}!")
            terrain[enemy_pos[1]][enemy_pos[0]] = '.'
            defeated_positions.append(enemy_pos)
            del active_enemies[enemy_pos]

    feedback = " ".join(messages) if messages else None
    return health, feedback, defeated_positions


def move_enemies_toward_player(terrain, active_enemies, player_x, player_y, map_pad, has_color):
    """Move active enemies one tile closer to the player if possible (within 3 tiles and max 5 moves)."""
    new_enemy_positions = {}
    occupied = set(active_enemies.keys())

    for (x, y), state in sorted(active_enemies.items(), key=lambda item: (item[0][1], item[0][0])):
        if state["health"] <= 0:
            continue

        # Check if player is within 3 tiles (Euclidean distance)
        dist_sq = (player_x - x) ** 2 + (player_y - y) ** 2
        if dist_sq > 9:  # 3^2 = 9
            new_enemy_positions[(x, y)] = state
            continue

        # Check if enemy has already moved 5 times
        if state.get("move_count", 0) >= 5:
            new_enemy_positions[(x, y)] = state
            continue

        dx = player_x - x
        dy = player_y - y
        step_x = (dx > 0) - (dx < 0)
        step_y = (dy > 0) - (dy < 0)
        move_candidates = []

        if abs(dx) >= abs(dy):
            if step_x:
                move_candidates.append((x + step_x, y))
            if step_y:
                move_candidates.append((x, y + step_y))
        else:
            if step_y:
                move_candidates.append((x, y + step_y))
            if step_x:
                move_candidates.append((x + step_x, y))

        if step_x and step_y:
            move_candidates.append((x + step_x, y + step_y))
        move_candidates.extend([
            (x - step_x, y),
            (x, y - step_y),
        ])

        moved = False
        for nx, ny in move_candidates:
            if (nx, ny) == (player_x, player_y):
                continue
            if ny < 0 or ny >= len(terrain) or nx < 0 or nx >= len(terrain[ny]):
                continue
            if terrain[ny][nx] != '.':
                continue
            if (nx, ny) in occupied:
                continue

            terrain[y][x] = '.'
            terrain[ny][nx] = state["tile"]
            try:
                map_pad.addch(y, x, ord('.'), get_tile_color('.', has_color))
                map_pad.addch(ny, nx, ord(state["tile"]), get_tile_color(state["tile"], has_color))
            except:
                pass
            state["move_count"] = state.get("move_count", 0) + 1
            new_enemy_positions[(nx, ny)] = state
            occupied.remove((x, y))
            occupied.add((nx, ny))
            moved = True
            break

        if not moved:
            new_enemy_positions[(x, y)] = state

    active_enemies.clear()
    active_enemies.update(new_enemy_positions)

COLLECTED_CHESTS = set()

command_buffer = ""
command_feedback = ""
health = 100
inventory_global = []

def handle_command(command, parameter):
    """Handle user commands from the command line.
    Args:
        command: The command word (e.g., 'use')
        parameter: Everything after the first word (e.g., 'health potion')
    """
    global command_feedback, health, inventory_global
    command = command.lower().strip()
    parameter = parameter.lower().strip()
    
    if command == "use":
        if parameter == "health potion":
            if "Health Potion" in inventory_global:
                inventory_global.remove("Health Potion")
                health += 50
                if health > 100:
                    health = 100
                command_feedback = f"Used Health Potion! Health: {health}"
            else:
                command_feedback = "You don't have a Health Potion!"
        else:
            command_feedback = f"Can't use: {parameter}"
    elif command == "":
        command_feedback = ""
    else:
        command_feedback = f"Unknown command: {command}"


def main(stdscr):
    # Setup
    curses.cbreak()  # Respond to keys immediately
    stdscr.keypad(True)  # Enable arrow keys
    curses.noecho()  # Don't echo key presses
    stdscr.nodelay(True)  # Non-blocking input (set True for non-blocking)
    curses.curs_set(0)  # Hide cursor
    
    # Turn-based timing (in milliseconds, 1000 = 1 second)
    turn_duration = 250
    last_turn_time = time.time() * 1000
    
    # Load all maps from external files
    MAPS = load_maps()
    
    # Current map tracking
    current_map = "forest"
    
    # Color setup
    has_color = False
    try:
        if curses.has_colors():
            curses.start_color()
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)      # Grass
            curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)      # Forest
            curses.init_pair(3, curses.COLOR_BLUE, curses.COLOR_BLACK)       # Water
            curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)        # Walls (brick red)
            curses.init_pair(5, curses.COLOR_YELLOW, curses.COLOR_BLACK)     # Doors (gold)
            curses.init_pair(6, curses.COLOR_YELLOW, curses.COLOR_BLACK)     # Chests (yellow)
            curses.init_pair(7, curses.COLOR_YELLOW, curses.COLOR_BLACK)     # Road (light brown/limestone)
            curses.init_pair(8, curses.COLOR_RED, curses.COLOR_BLACK)        # Enemies
            has_color = True
    except:
        has_color = False
    
    # Get terminal size
    max_y, max_x = stdscr.getmaxyx()
    inventory_width = min(22, max(12, max_x // 4))
    inventory_x = max_x - inventory_width
    map_display_width = max(10, max_x - inventory_width)
    status_row = 0
    map_display_top = 1
    map_display_bottom = max_y - 2 if max_y >= 3 else max_y - 1
    message_row = max_y - 1
    inventory_top = 1
    inventory_bottom = max_y - 2 if max_y >= 3 else max_y - 1
    map_display_height = max(1, map_display_bottom - map_display_top + 1)

    ########################################################################################inventory!
    swords = ["Old Sword", "Blunt Longsword", "Arming Sword", "Fine Longsword", "Masterwork Longsword", "Legendary Longsword"] ###swords[0] will have the damage of damage[0]
    damageList = [1, 2, 3, 5, 7, 10]
    armor = ["Leather Garments", "Padded Armour", "Studded Leather", "Chainmail Suit", "Old Cuirass", "Legendary Plate Armour"] ###armor[0] will have the defense of defense[0]
    defenseList = [1, 2, 3, 5, 7, 10]
    inventory = [
        "Old Sword",
        "Leather Garments",
        "Health Potion",
    ]
    playerAttack = damageList[0]
    playerDefence = defenseList[0]
    gold = 0
    global inventory_global, health
    inventory_global = inventory
    health = 100

    # Load the current map from MAPS dictionary
    terrain = [row[:] for row in MAPS[current_map]]  # Deep copy the map data
    
    # Get map dimensions
    map_height = len(terrain)
    map_width = max(len(row) for row in terrain) if terrain else 0
    
    # Pad rows to same width if needed
    for row in terrain:
        while len(row) < map_width:
            row.append('.')
    
    # Create map (Pad = virtual surface larger than screen)
    map_pad = curses.newpad(map_height, map_width)
    
    # Draw the map
    for y in range(map_height):
        for x in range(map_width):
            if x < len(terrain[y]):
                char = terrain[y][x]
                attr = get_tile_color(char, has_color)
                
                try:
                    map_pad.addch(y, x, ord(char), attr)
                except:
                    pass

    active_enemies = initialize_enemies(terrain)
    
    # Player starting positions for each map
    SPAWN_POINTS = {
        "forest": (2, 4),
    }
    
    # Player position - use the spawn tile if present, otherwise fallback to points
    spawn = find_spawn_point(terrain)
    if spawn is not None:
        player_x, player_y = spawn
    elif current_map in SPAWN_POINTS:
        player_x, player_y = SPAWN_POINTS[current_map]
    else:
        player_x, player_y = (2, 1)
    
    old_player_x, old_player_y = player_x, player_y
    
    # Camera offset (what part of the map we're viewing)
    camera_x, camera_y = 0, 0
    
    # Command line state
    command_buffer_local = ""
    command_feedback_local = ""
    feedback_expires_at = 0
    feedback_duration = 1000  # milliseconds
    
    # Game loop
    running = True
    last_key = None
    while running:
        # Center camera on player
        camera_x = max(0, min(player_x - map_display_width // 2, map_width - map_display_width))
        camera_y = max(0, min(player_y - map_display_height // 2, map_height - map_display_height))
        
        # Redraw player at current position
        map_pad.addch(player_y, player_x, ord('@'), curses.A_BOLD)
        
        # Clear the screen before refresh so smaller maps don't leave old tiles behind
        stdscr.erase()
        stdscr.refresh()
        draw_status_bar(stdscr, health, playerAttack, playerDefence, gold, max_x)
        # Display the map portion visible on screen
        # refresh(pad_top_row, pad_left_col, screen_top_row, screen_left_col, screen_bottom_row, screen_right_col)
        safe_pad_refresh(map_pad, camera_y, camera_x, map_display_top, 0, map_display_bottom, map_display_width - 1, max_y, max_x, map_height, map_width)

        # Draw fixed inventory sidebar on the right, reserving the top status bar and bottom input line
        if inventory_x >= 0:
            draw_inventory_sidebar(stdscr, inventory_global, inventory_x, inventory_width, inventory_top, inventory_bottom)

        # Draw command line at the bottom with feedback, current input, or nearby door hints
        door_feedback = adjacent_locked_door_message(current_map, terrain, player_x, player_y, inventory_global)
        try:
            if command_feedback_local:
                display_text = command_feedback_local
            elif command_buffer_local:
                display_text = "> " + command_buffer_local
            elif door_feedback:
                display_text = door_feedback
            else:
                display_text = ""
            stdscr.addstr(message_row, 0, display_text.ljust(max_x)[:max_x])
        except curses.error:
            pass
        stdscr.refresh()
        
        # Handle input (non-blocking - collect keys)
        try:
            key = stdscr.getch()
            if key != -1:  # -1 means no key pressed
                if key == ord('q'):
                    running = False
                elif key == ord('\n') or key == curses.KEY_ENTER:  # Enter to execute command
                    if command_buffer_local.strip():
                        parts = command_buffer_local.strip().split(None, 1)  # Split on first space
                        cmd = parts[0]
                        param = parts[1] if len(parts) > 1 else ""
                        handle_command(cmd, param)
                        command_feedback_local = command_feedback
                        feedback_expires_at = time.time() * 1000 + feedback_duration
                    command_buffer_local = ""
                elif key == curses.KEY_BACKSPACE or key == 127 or key == 8:  # Backspace
                    command_buffer_local = command_buffer_local[:-1]
                    command_feedback_local = ""
                elif 32 <= key <= 126:  # Printable ASCII characters
                    command_buffer_local += chr(key)
                    command_feedback_local = ""
                # Movement keys still work
                elif key in [curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT]:
                    last_key = key  # Store for processing on next turn
        except:
            pass
        
        current_time = time.time() * 1000
        if command_feedback_local and current_time >= feedback_expires_at:
            command_feedback_local = ""
        
        # Process turn-based movement every X milliseconds
        current_time = time.time() * 1000
        if current_time - last_turn_time >= turn_duration:
            last_turn_time = current_time

            # Automatic combat if enemies are adjacent
            move_enemies_toward_player(terrain, active_enemies, player_x, player_y, map_pad, has_color)
            health, combat_feedback, defeated_positions = process_adjacent_enemy_combat(
                terrain,
                player_x,
                player_y,
                active_enemies,
                playerAttack,
                playerDefence,
                health,
            )
            if defeated_positions:
                for dead_x, dead_y in defeated_positions:
                    if 0 <= dead_y < map_height and 0 <= dead_x < map_width:
                        try:
                            map_pad.addch(dead_y, dead_x, ord('.'), get_tile_color('.', has_color))
                        except:
                            pass
            if combat_feedback:
                command_feedback_local = combat_feedback
                feedback_expires_at = time.time() * 1000 + feedback_duration

            # Process movement from last key pressed (only arrow keys)
            if last_key is not None:
                old_player_x, old_player_y = player_x, player_y
                new_player_x, new_player_y = player_x, player_y
                map_changed = False
                
                # Calculate new position based on key
                if last_key == curses.KEY_UP and player_y > 0:
                    new_player_y -= 1
                elif last_key == curses.KEY_DOWN and player_y < map_height - 1:
                    new_player_y += 1
                elif last_key == curses.KEY_LEFT and player_x > 0:
                    new_player_x -= 1
                elif last_key == curses.KEY_RIGHT and player_x < map_width - 1:
                    new_player_x += 1
                
                # Only move if the destination is walkable
                if is_walkable(terrain, current_map, new_player_x, new_player_y):
                    #####################dialogue check
                    if terrain[new_player_y][new_player_x] == '8' and (current_map, new_player_x, new_player_y) in PEOPLE: #dialogue check
                        command_feedback_local = PEOPLE[(current_map, new_player_x, new_player_y)]
                        feedback_expires_at = time.time() * 1000 + feedback_duration
                    elif terrain[new_player_y][new_player_x] == '|' and (current_map, new_player_x, new_player_y) in LOCKS:
                        unlocked, required_key = unlock_door(current_map, new_player_x, new_player_y, inventory_global)
                        if unlocked:
                            command_feedback_local = f"Used {required_key} to unlock the door."
                            feedback_expires_at = time.time() * 1000 + feedback_duration
                        else:
                            # Block movement if the door is still locked
                            last_key = None
                            command_feedback_local = f"Locked door. Need {LOCKS[(current_map, new_player_x, new_player_y)]}."
                            feedback_expires_at = time.time() * 1000 + feedback_duration
                            continue
                    player_x = new_player_x
                    player_y = new_player_y

                    #####################checks for tiles
                    # Check for chest pickup on the current tile
                    if terrain[player_y][player_x] == '=':
                        loot = pickup_chest(current_map, player_x, player_y, terrain, inventory_global)
                        if loot:
                            command_feedback_local = f"Picked up {loot}!"
                            feedback_expires_at = time.time() * 1000 + feedback_duration

                    # Check for door entry after movement
                    if terrain[player_y][player_x] == 'X':
                        door_key = (current_map, player_x, player_y)
                        if door_key in DOORS:
                            # Travel through door
                            dest_map, dest_x, dest_y = DOORS[door_key]
                            current_map = dest_map
                            player_x, player_y = dest_x, dest_y
                            map_changed = True
                            
                            # Reload the map
                            terrain = [row[:] for row in MAPS[current_map]]  # Deep copy the map data
                            map_height = len(terrain)
                            map_width = max(len(row) for row in terrain) if terrain else 0
                            for row in terrain:
                                while len(row) < map_width:
                                    row.append('.')
                            
                            # Redraw map
                            map_pad = curses.newpad(map_height, map_width)
                            for y in range(map_height):
                                for x in range(map_width):
                                    if x < len(terrain[y]):
                                        char = terrain[y][x]
                                        attr = get_tile_color(char, has_color)
                                        try:
                                            map_pad.addch(y, x, ord(char), attr)
                                        except:
                                            pass
                            active_enemies = initialize_enemies(terrain)
                            # Clear screen and refresh
                            stdscr.erase()
                            stdscr.refresh()
                            # Draw player at new location
                            map_pad.addch(player_y, player_x, ord('@'), curses.A_BOLD)
                            # Force immediate display update using safe bounds
                            safe_pad_refresh(map_pad, 0, 0, map_display_top, 0, map_display_bottom, map_display_width - 1, max_y, max_x, map_height, map_width)
                
                # Restore terrain at old player position
                if not map_changed and (old_player_x, old_player_y) != (player_x, player_y):
                    if 0 <= old_player_y < len(terrain) and 0 <= old_player_x < len(terrain[old_player_y]):
                        old_char = terrain[old_player_y][old_player_x]
                        attr = get_tile_color(old_char, has_color)
                        try:
                            map_pad.addch(old_player_y, old_player_x, ord(old_char), attr)
                        except:
                            pass
                
                # Draw player at new position
                map_pad.addch(player_y, player_x, ord('@'), curses.A_BOLD)
                
                last_key = None  # Consume the key after processing
        
        # Small sleep to prevent CPU spinning
        time.sleep(0.01)
        
        try:
            pass
        except KeyboardInterrupt:
            running = False
    
# Initialize and run
stdscr = curses.initscr()
try:
    main(stdscr)
finally:
    # Restore terminal to original state
    curses.nocbreak()
    stdscr.keypad(False)
    curses.echo()
    curses.endwin()
    ####made by josh with significant help from chatgpt! hope you enjoy the game! :)####