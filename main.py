import os, random, curses, time

def is_walkable(terrain, x, y):
    """Check if a tile is walkable (not a collision tile)"""
    if x < 0 or y < 0 or x >= len(terrain[0]) or y >= len(terrain):
        return False
    tile = terrain[y][x]
    # Blocked tiles: forest (#), water (~), walls (%)
    return tile not in ['#', '~', '%']

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
            has_color = True
    except:
        has_color = False
    
    # Get terminal size
    max_y, max_x = stdscr.getmaxyx()
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
    
    # Player starting positions for each map
    SPAWN_POINTS = {
        "forest": (1, 4),
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
    
    # Game loop
    running = True
    last_key = None
    while running:
        # Center camera on player
        camera_x = max(0, min(player_x - max_x // 2, map_width - max_x))
        camera_y = max(0, min(player_y - max_y // 2, map_height - max_y))
        
        # Redraw player at current position
        map_pad.addch(player_y, player_x, ord('@'), curses.A_BOLD)
        
        # Clear the screen before refresh so smaller maps don't leave old tiles behind
        stdscr.erase()
        stdscr.refresh()
        # Display the map portion visible on screen
        # refresh(pad_top_row, pad_left_col, screen_top_row, screen_left_col, screen_bottom_row, screen_right_col)
        safe_pad_refresh(map_pad, camera_y, camera_x, 0, 0, max_y - 1, max_x - 1, max_y, max_x, map_height, map_width)
        
        # Handle input (non-blocking - collect keys but don't process yet)
        try:
            key = stdscr.getch()
            if key != -1:  # -1 means no key pressed
                if key == ord('q'):
                    running = False
                elif key == ord(' '):  # Spacebar for interact
                    # Could add chest opening or other interactions here
                    pass
                else:
                    last_key = key  # Store for processing on next turn
        except:
            pass
        
        # Process turn-based movement every X milliseconds
        current_time = time.time() * 1000
        if current_time - last_turn_time >= turn_duration:
            last_turn_time = current_time
            
            # Process movement from last key pressed
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
                if is_walkable(terrain, new_player_x, new_player_y):
                    player_x = new_player_x
                    player_y = new_player_y
                    
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
                            # Clear screen and refresh
                            stdscr.erase()
                            stdscr.refresh()
                            # Draw player at new location
                            map_pad.addch(player_y, player_x, ord('@'), curses.A_BOLD)
                            # Force immediate display update using safe bounds
                            safe_pad_refresh(map_pad, 0, 0, 0, 0, max_y - 1, max_x - 1, max_y, max_x, map_height, map_width)
                
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