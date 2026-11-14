#!/usr/bin/env python3
"""Add Windows-style keyboard shortcuts to the XFCE defaults in a root file system.

Usage: patch-xfce-defaults.py <rootfs>

Shortcuts added (on top of the XFCE defaults):
  Windows key          open the Start menu
  Windows + E          open the file manager
  Windows + R          "Run" dialog
  Windows + D          show the desktop
  Windows + L          log out screen
  Windows + Left/Right snap a window to half the screen
  Windows + Up/Down    maximise / minimise
  Ctrl + Shift + Esc   Task manager
  Ctrl + Alt + Delete  Task manager
  Print Screen         screenshot
"""
import sys
import xml.etree.ElementTree as ET

COMMANDS = {
    "Super_L": "xfce4-popup-whiskermenu",
    "<Super>e": "thunar",
    "<Super>r": "xfce4-appfinder --collapsed",
    "<Super>l": "xfce4-session-logout",
    "<Primary><Shift>Escape": "xfce4-taskmanager",
    "<Primary><Alt>Delete": "xfce4-taskmanager",
    "Print": "xfce4-screenshooter",
}
WINDOW_MANAGER = {
    "<Super>d": "show_desktop_key",
    "<Super>Left": "tile_left_key",
    "<Super>Right": "tile_right_key",
    "<Super>Up": "maximize_window_key",
    "<Super>Down": "hide_window_key",
}


def child(parent, name):
    for prop in parent.findall("property"):
        if prop.get("name") == name:
            return prop
    prop = ET.SubElement(parent, "property", {"name": name, "type": "empty"})
    return prop


def set_shortcut(section, key, value):
    for prop in list(section.findall("property")):
        # Drop any existing binding of the same key or the same action
        # (only for window-manager actions, which must be unique).
        if prop.get("name") == key:
            section.remove(prop)
    ET.SubElement(section, "property", {"name": key, "type": "string", "value": value})


def main(rootfs):
    path = f"{rootfs}/etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-keyboard-shortcuts.xml"
    tree = ET.parse(path)
    channel = tree.getroot()
    for group, shortcuts in (("commands", COMMANDS), ("xfwm4", WINDOW_MANAGER)):
        group_prop = child(channel, group)
        for section_name in ("default", "custom"):
            section = child(group_prop, section_name)
            for key, value in shortcuts.items():
                set_shortcut(section, key, value)
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    print(f"patched {path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
