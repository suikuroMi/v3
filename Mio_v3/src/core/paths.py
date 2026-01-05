import os
import sys

def get_project_root():
    """
    Returns the absolute path to the 'Mio_v3' root folder.
    It works by finding THIS file's location and going up 2 levels.
    (src/core/paths.py -> src/core -> src -> ROOT)
    """
    # This file is in .../Mio_v3/src/core/paths.py
    current_file = os.path.abspath(__file__)
    src_core = os.path.dirname(current_file) # .../src/core
    src = os.path.dirname(src_core)          # .../src
    root = os.path.dirname(src)              # .../Mio_v3
    return root

def get_asset_path(filename):
    """
    Smartly finds an asset (image/sound) by name.
    """
    root = get_project_root()
    
    # 1. Check in assets/avatars (Primary for images)
    avatar_path = os.path.join(root, "assets", "avatars", filename)
    if os.path.exists(avatar_path): 
        return avatar_path
        
    # 2. Check in assets (General)
    general_path = os.path.join(root, "assets", filename)
    if os.path.exists(general_path): 
        return general_path
        
    # 3. Check in assets/sounds
    sound_path = os.path.join(root, "assets", "sounds", filename)
    if os.path.exists(sound_path): 
        return sound_path
        
    return None # Not found