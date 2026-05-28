#!/usr/bin/env python3
"""
Fix skin_5_c0 and skin_2_c0 elements in heblu.bbmodel:
- Apply 180° Y-axis rotation around pivot point
- Swap face UVs: north↔south, east↔west
- Rotate up/down face UVs 180° in UV space
- Change bone rotation for skin_2 and skin_5 groups from [0, 0, 180] to [0, 0, 0]
"""

import json
import copy

INPUT_FILE = "/home/z/my-project/MROLF-TGNBF/derived/heblu.bbmodel"

def rotate_y_180_around_pivot(point, pivot):
    """Apply 180° Y-axis rotation around pivot: (x,y,z) → (-x, y, -z) relative to pivot."""
    rel = [point[0] - pivot[0], point[1] - pivot[1], point[2] - pivot[2]]
    rotated = [-rel[0], rel[1], -rel[2]]
    return [rotated[0] + pivot[0], rotated[1] + pivot[1], rotated[2] + pivot[2]]

def swap_faces(faces, face_a, face_b):
    """Swap two faces in the faces dict."""
    if face_a in faces and face_b in faces:
        faces[face_a], faces[face_b] = faces[face_b], faces[face_a]
    elif face_a in faces:
        faces[face_b] = faces.pop(face_a)
    elif face_b in faces:
        faces[face_a] = faces.pop(face_b)

def rotate_uv_180(uv):
    """Rotate UV 180° in UV space: [u1, v1, u2, v2] → [u2, v2, u1, v1]."""
    if isinstance(uv, list) and len(uv) == 4:
        return [uv[2], uv[3], uv[0], uv[1]]
    return uv

def main():
    # Read the file
    print(f"Reading {INPUT_FILE}...")
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)
    
    # Find elements to fix
    elements = data.get("elements", [])
    target_names = {"skin_5_c0", "skin_2_c0"}
    found = {}
    
    for elem in elements:
        name = elem.get("name", "")
        if name in target_names:
            found[name] = elem
    
    print(f"Found elements: {list(found.keys())}")
    
    for name, elem in found.items():
        from_pos = elem["from"]
        to_pos = elem["to"]
        origin = elem.get("origin", [0, 0, 0])
        
        print(f"\n--- Processing {name} ---")
        print(f"  Original from: {from_pos}")
        print(f"  Original to:   {to_pos}")
        print(f"  Pivot (origin): {origin}")
        
        # Apply Y-180° rotation around pivot
        new_from = rotate_y_180_around_pivot(from_pos, origin)
        new_to = rotate_y_180_around_pivot(to_pos, origin)
        
        print(f"  Rotated from: {new_from}")
        print(f"  Rotated to:   {new_to}")
        
        # Ensure from ≤ to on each axis (swap if needed)
        for i in range(3):
            if new_from[i] > new_to[i]:
                new_from[i], new_to[i] = new_to[i], new_from[i]
        
        print(f"  Final from:   {new_from}")
        print(f"  Final to:     {new_to}")
        
        # Update element
        elem["from"] = new_from
        elem["to"] = new_to
        
        # Swap face UVs: north↔south, east↔west
        faces = elem.get("faces", {})
        swap_faces(faces, "north", "south")
        swap_faces(faces, "east", "west")
        
        # For up/down faces, rotate UV 180° in UV space
        for face_name in ["up", "down"]:
            if face_name in faces:
                face = faces[face_name]
                uv = face.get("uv")
                if uv is not None:
                    face["uv"] = rotate_uv_180(uv)
                    print(f"  Rotated {face_name} face UV: {uv} → {face['uv']}")
        
        print(f"  Face directions after swap: {list(faces.keys())}")
    
    # Fix bone rotations for groups named "skin_2" and "skin_5"
    # Groups are stored in data["groups"], not the outliner
    target_groups = {"skin_2", "skin_5"}
    
    print("\n--- Fixing group rotations ---")
    for group in data.get("groups", []):
        name = group.get("name", "")
        if name in target_groups:
            old_rot = group.get("rotation", [0, 0, 0])
            print(f"  Group '{name}' rotation: {old_rot} → [0, 0, 0]")
            group["rotation"] = [0, 0, 0]
    
    # Save back
    print(f"\nSaving to {INPUT_FILE}...")
    with open(INPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    
    print("Done!")

if __name__ == "__main__":
    main()
