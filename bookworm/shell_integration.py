# coding: utf-8

import System
import sys
import os
from typing import Iterable
from dataclasses import dataclass
from functools import wraps
from bookworm import app
from bookworm.paths import app_path
from bookworm.reader import EBookReader
from bookworm.utils import ignore
from bookworm.vendor import shellapi
from bookworm.win_registry import RegKey, RegistryValueKind
from bookworm.logger import logger


log = logger.getChild(__name__)


def get_ext_info(supported="*"):
    ficos_path = app_path("resources", "icons")
    doctypes = {}
    for cls in EBookReader.document_classes:
        for ext in cls.extensions:
            cext = ext.replace("*", "")
            if (supported == "*") or (cext in supported):
                icon = ficos_path.joinpath(cls.format + ".ico")
                icon = str(icon) if icon.exists() else None
                doctypes[cext] = (f"{app.prog_id}.{cls.format}", _(cls.name), icon)
    return doctypes


def add_shell_command(key, executable):
    key.CreateSubKey(r"shell\Open\Command").SetValue(
        "", f'"{executable}" "%1"', RegistryValueKind.String
    )


def register_application(prog_id, executable, supported_exts):
    exe = os.path.split(executable)[-1]
    with RegKey.LocalSoftware(fr"Applications\{exe}", ensure_created=True) as exe_key:
        add_shell_command(exe_key, executable)
        with RegKey(exe_key, "SupportedTypes", ensure_created=True) as supkey:
            for ext in get_ext_info(supported_exts):
                supkey.SetValue(ext, "", RegistryValueKind.String)


def associate_extension(ext, prog_id, executable, desc, icon=None):
    # Add the prog_id
    with RegKey.LocalSoftware(prog_id, ensure_created=True) as progkey:
        progkey.SetValue("", desc)
        with RegKey(progkey, "DefaultIcon", ensure_created=True) as iconkey:
            iconkey.SetValue("", icon or executable)
        add_shell_command(progkey, executable)
    # Associate file type
    with RegKey.LocalSoftware(fr"{ext}\OpenWithProgids", ensure_created=True) as askey:
        askey.SetValue(prog_id, System.Array[System.Byte]([]), RegistryValueKind.Binary)
    # Set this executable as the default handler for files with this extension
    with RegKey.LocalSoftware(ext, ensure_created=True) as defkey:
        defkey.SetValue("", prog_id)
    shellapi.SHChangeNotify(
        shellapi.SHCNE_ASSOCCHANGED, shellapi.SHCNF_IDLIST, None, None
    )


def remove_association(ext, prog_id):
    try:
        with RegKey.LocalSoftware("") as k:
            k.DeleteSubKeyTree(prog_id)
    except System.ArgumentException:
        log.exception(f"Faild to remove the prog_id key", exc_info=True)
    try:
        with RegKey.LocalSoftware(fr"{ext}\OpenWithProgids") as k:
            k.DeleteSubKey(prog_id)
    except System.ArgumentException:
        log.exception(f"Faild to remove the openwith prog_id key", exc_info=True)
    shellapi.SHChangeNotify(
        shellapi.SHCNE_ASSOCCHANGED, shellapi.SHCNF_IDLIST, None, None
    )


@ignore(System.Exception)
def shell_integrate(supported="*"):
    if not app.is_frozen:
        return log.warning(
            "File association is not available when running from source."
        )
    log.info(f"Registring file associations for extensions {supported}.")
    register_application(app.prog_id, sys.executable, supported)
    doctypes = get_ext_info(supported)
    for (ext, (prog_id, desc, icon)) in doctypes.items():
        associate_extension(ext, prog_id, sys.executable, desc, icon)


@ignore(System.Exception)
def shell_disintegrate(supported="*"):
    if not app.is_frozen:
        return log.warning(
            "File association is not available when running from source."
        )
    log.info(f"Unregistring file associations for extensions {supported}.")
    exe = os.path.split(sys.executable)[-1]
    with RegKey.LocalSoftware("Applications") as apps_key:
        should_remove = False
        with RegKey(apps_key, exe) as exe_key:
            should_remove = exe_key.exists
        if should_remove:
            apps_key.DeleteSubKeyTree(exe)
    doctypes = get_ext_info(supported)
    for (ext, (prog_id, desc, icon)) in doctypes.items():
        remove_association(ext, prog_id)
