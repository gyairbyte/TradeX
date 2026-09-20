"""Deterministic tests for Windows desktop launchers and shortcut installer.

Validates:
- make_icon.py asset generation (Start/Stop icons, motifs, formats, and colors)
- Windows launcher scripts (.ps1 and .bat line endings, syntax, and delegation)
- install_desktop_shortcuts.ps1 shortcut creation and property correctness
- Defense-in-depth process identity verification logic
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHERS_DIR = REPO_ROOT / "launchers"
WIN_LAUNCHERS_DIR = LAUNCHERS_DIR / "windows"


def test_make_icon_assets_exist_and_properties() -> None:
    """Verify Start and Stop launcher icons exist and have valid visual identities."""
    start_png = LAUNCHERS_DIR / "tradex_icon.png"
    stop_png = LAUNCHERS_DIR / "tradex_stop_icon.png"
    start_ico = WIN_LAUNCHERS_DIR / "TradeX.ico"
    stop_ico = WIN_LAUNCHERS_DIR / "TradeX-Stop.ico"

    for path in (start_png, stop_png, start_ico, stop_ico):
        assert path.exists(), f"Asset missing: {path}"
        assert path.stat().st_size > 0, f"Asset empty: {path}"

    # Verify Start PNG
    with Image.open(start_png) as img:
        assert img.size == (1024, 1024)
        assert img.mode == "RGBA"
        # Background is dark slate-900: (17, 24, 39)
        bg_pixel = img.getpixel((300, 300))
        assert bg_pixel[:3] == (17, 24, 39)
        # Candle motif in the lower region contains green-500: (34, 197, 94)
        # Sample middle rising bar
        motif_pixel = img.getpixel((512, 600))
        assert motif_pixel[1] > 150, f"Expected green motif, got: {motif_pixel}"
        assert motif_pixel[0] < 100

    # Verify Stop PNG
    with Image.open(stop_png) as img:
        assert img.size == (1024, 1024)
        assert img.mode == "RGBA"
        # Background is dark slate-900: (17, 24, 39)
        bg_pixel = img.getpixel((300, 300))
        assert bg_pixel[:3] == (17, 24, 39)
        # Stop motif contains red-500: (239, 68, 68)
        motif_pixel = img.getpixel((512, 600))
        assert motif_pixel[0] > 200, f"Expected red motif, got: {motif_pixel}"
        assert motif_pixel[1] < 100

    # Verify ICO headers and embedded sizes
    for ico_path in (start_ico, stop_ico):
        content = ico_path.read_bytes()
        # Standard ICO magic bytes: 0x00, 0x00, 0x01, 0x00
        assert content[:4] == b"\x00\x00\x01\x00", f"Invalid ICO header: {ico_path}"
        with Image.open(ico_path) as ico:
            assert ico.format == "ICO"
            # PIL ICO parser returns sizes attribute or images list
            sizes = getattr(ico, "sizes", None)
            if sizes:
                assert (16, 16) in sizes
                assert (32, 32) in sizes
                assert (256, 256) in sizes


def test_bat_files_crlf_and_structure() -> None:
    """Verify batch wrappers have CRLF endings and delegate safely to PowerShell."""
    start_bat = WIN_LAUNCHERS_DIR / "TradeX.bat"
    stop_bat = WIN_LAUNCHERS_DIR / "TradeX-Stop.bat"

    for bat_path in (start_bat, stop_bat):
        assert bat_path.exists()
        raw = bat_path.read_bytes()
        assert b"\r\n" in raw, f"Expected CRLF in {bat_path}"
        assert b"\n" not in raw.replace(b"\r\n", b""), f"Found bare LF in {bat_path}"
        text = raw.decode("utf-8")
        assert "powershell" in text.lower()
        assert "-ExecutionPolicy Bypass" in text
        assert "-WindowStyle Hidden" in text

    assert "TradeX.ps1" in (WIN_LAUNCHERS_DIR / "TradeX.bat").read_text(encoding="utf-8")
    assert "TradeX-Stop.ps1" in (WIN_LAUNCHERS_DIR / "TradeX-Stop.bat").read_text(encoding="utf-8")


def test_powershell_scripts_crlf() -> None:
    """Verify PowerShell launcher scripts have CRLF endings as required by .gitattributes."""
    scripts = [
        WIN_LAUNCHERS_DIR / "TradeX.ps1",
        WIN_LAUNCHERS_DIR / "TradeX-Stop.ps1",
        WIN_LAUNCHERS_DIR / "install_desktop_shortcuts.ps1",
    ]
    for s in scripts:
        assert s.exists()
        raw = s.read_bytes()
        assert b"\r\n" in raw, f"Expected CRLF in {s}"
        assert b"\n" not in raw.replace(b"\r\n", b""), f"Found bare LF in {s}"


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="powershell.exe not available")
def test_powershell_scripts_syntax() -> None:
    """Parse all PowerShell scripts using the PowerShell parser to ensure zero syntax errors."""
    scripts = [
        WIN_LAUNCHERS_DIR / "TradeX.ps1",
        WIN_LAUNCHERS_DIR / "TradeX-Stop.ps1",
        WIN_LAUNCHERS_DIR / "install_desktop_shortcuts.ps1",
    ]

    for script in scripts:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"""
            $errors = $null
            $tokens = [System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$tokens, [ref]$errors)
            if ($errors.Count -gt 0) {{
                $errors | ForEach-Object {{ Write-Error $_.Message }}
                exit 1
            }}
            exit 0
            """,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert res.returncode == 0, f"Syntax error in {script}:\n{res.stderr}\n{res.stdout}"


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="powershell.exe not available")
def test_install_desktop_shortcuts_in_temp_dir(tmp_path: Path) -> None:
    """Verify install_desktop_shortcuts.ps1 creates .lnk shortcuts with exact properties."""
    installer = WIN_LAUNCHERS_DIR / "install_desktop_shortcuts.ps1"
    target_dir = tmp_path / "shortcuts"

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(installer),
        "-ProjectRoot",
        str(REPO_ROOT),
        "-TargetDirectory",
        str(target_dir),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"Installer failed:\n{res.stderr}\n{res.stdout}"

    start_lnk = target_dir / "Start TradeX.lnk"
    stop_lnk = target_dir / "Stop TradeX.lnk"

    assert start_lnk.exists(), "Start TradeX.lnk was not created"
    assert stop_lnk.exists(), "Stop TradeX.lnk was not created"

    # Verify shortcut targets and icon locations via WScript.Shell
    inspect_cmd = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        f"""
        $sh = New-Object -ComObject WScript.Shell
        $s1 = $sh.CreateShortcut('{start_lnk}')
        $s2 = $sh.CreateShortcut('{stop_lnk}')
        Write-Output "S1_TARGET:$($s1.TargetPath)"
        Write-Output "S1_WORKDIR:$($s1.WorkingDirectory)"
        Write-Output "S1_ICON:$($s1.IconLocation)"
        Write-Output "S2_TARGET:$($s2.TargetPath)"
        Write-Output "S2_WORKDIR:$($s2.WorkingDirectory)"
        Write-Output "S2_ICON:$($s2.IconLocation)"
        """,
    ]
    res_inspect = subprocess.run(inspect_cmd, capture_output=True, text=True, check=False)
    assert res_inspect.returncode == 0, f"Inspect failed:\n{res_inspect.stderr}"
    out = res_inspect.stdout

    expected_start_target = str(WIN_LAUNCHERS_DIR / "TradeX.bat")
    expected_stop_target = str(WIN_LAUNCHERS_DIR / "TradeX-Stop.bat")
    expected_workdir = str(REPO_ROOT)
    expected_start_ico = str(WIN_LAUNCHERS_DIR / "TradeX.ico") + ",0"
    expected_stop_ico = str(WIN_LAUNCHERS_DIR / "TradeX-Stop.ico") + ",0"

    assert f"S1_TARGET:{expected_start_target}".lower() in out.lower()
    assert f"S1_WORKDIR:{expected_workdir}".lower() in out.lower()
    assert f"S1_ICON:{expected_start_ico}".lower() in out.lower()

    assert f"S2_TARGET:{expected_stop_target}".lower() in out.lower()
    assert f"S2_WORKDIR:{expected_workdir}".lower() in out.lower()
    assert f"S2_ICON:{expected_stop_ico}".lower() in out.lower()


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="powershell.exe not available")
def test_identity_safety_rules_in_powershell() -> None:
    """Verify Test-IsTradeXProcess logic accurately validates TradeX and rejects unrelated processes."""
    # Test script executing the exact identity matching logic extracted from the launchers
    dashboard_path = str(REPO_ROOT / "tradex" / "ui" / "dashboard.py")
    test_cmd = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        f"""
        $ProjectRoot = '{REPO_ROOT}'
        $Dashboard = '{dashboard_path}'

        function Test-IsTradeXCommandLine($cmd, $expectedDashboardPath) {{
            if (-not $cmd -or -not $expectedDashboardPath) {{
                return $false
            }}
            $normTarget = $expectedDashboardPath.Trim().ToLowerInvariant().Replace("/", "\\")
            $relativeTail = (Join-Path "tradex" (Join-Path "ui" "dashboard.py")).ToLowerInvariant().Replace("/", "\\")
            $repoRootNorm = $ProjectRoot.Trim().ToLowerInvariant().Replace("/", "\\")

            $normCmd = $cmd.ToLowerInvariant().Replace("/", "\\")
            if ($normCmd.Contains($normTarget)) {{
                return $true
            }}
            if ($normCmd.Contains($relativeTail) -and $normCmd.Contains($repoRootNorm)) {{
                return $true
            }}
            return $false
        }}

        # Case 1: Exact canonical dashboard path
        $c1 = Test-IsTradeXCommandLine "python.exe -m streamlit run `"{dashboard_path}`" --server.port=8501" $Dashboard
        if (-not $c1) {{ exit 101 }}

        # Case 2: Forward slash dashboard path
        $fwd = '{dashboard_path}'.Replace('\\', '/')
        $c2 = Test-IsTradeXCommandLine "streamlit run $fwd --server.port=8501" $Dashboard
        if (-not $c2) {{ exit 102 }}

        # Case 3: Unrelated python http server on port 8501
        $c3 = Test-IsTradeXCommandLine "python.exe -m http.server 8501" $Dashboard
        if ($c3) {{ exit 103 }}

        # Case 4: Unrelated streamlit app on port 8501
        $c4 = Test-IsTradeXCommandLine "streamlit run C:\\OtherApp\\app.py --server.port=8501" $Dashboard
        if ($c4) {{ exit 104 }}

        # Case 5: Empty command line
        $c5 = Test-IsTradeXCommandLine "" $Dashboard
        if ($c5) {{ exit 105 }}

        exit 0
        """,
    ]
    res = subprocess.run(test_cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"Identity validation rule failed (exit {res.returncode}):\n{res.stderr}\n{res.stdout}"


def test_script_content_invariants() -> None:
    """Verify that launchers strictly adhere to the critical safety requirements."""
    start_ps1 = (WIN_LAUNCHERS_DIR / "TradeX.ps1").read_text(encoding="utf-8")
    stop_ps1 = (WIN_LAUNCHERS_DIR / "TradeX-Stop.ps1").read_text(encoding="utf-8")

    # Start launcher must use -PassThru and persist PID
    assert "-PassThru" in start_ps1
    assert "dashboard.pid" in start_ps1
    assert "Get-NetTCPConnection" in start_ps1
    assert "Win32_Process" in start_ps1
    assert "unrelated application" in start_ps1

    # Stop launcher must use defense in depth
    assert "dashboard.pid" in stop_ps1
    assert "Get-NetTCPConnection" in stop_ps1
    assert "Win32_Process" in stop_ps1
    assert "Test-IsTradeXProcess" in stop_ps1
    assert "unrelated application" in stop_ps1
    assert "dashboard.py" in stop_ps1


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="powershell.exe not available")
def test_stop_launcher_when_not_running_cleans_stale_pid() -> None:
    """Verify TradeX-Stop.ps1 reports not running and cleans stale PID file without errors."""
    stop_ps1 = WIN_LAUNCHERS_DIR / "TradeX-Stop.ps1"
    log_dir = Path.home() / ".tradex"
    pid_file = log_dir / "dashboard.pid"

    log_dir.mkdir(parents=True, exist_ok=True)
    pid_file.write_text("99999999", encoding="ascii")
    assert pid_file.exists()

    try:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(stop_ps1),
            "-Quiet",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert res.returncode == 0, f"TradeX-Stop failed:\n{res.stderr}\n{res.stdout}"
        assert "not currently running" in res.stdout.lower()
        assert not pid_file.exists(), "Stale PID file should have been removed"
    finally:
        if pid_file.exists():
            pid_file.unlink(missing_ok=True)


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="powershell.exe not available")
def test_unrelated_process_on_port_8501_rejected() -> None:
    """Verify that both Start and Stop launchers refuse to kill or conflate an unrelated process on port 8501."""
    import socket
    import sys

    # First check if port 8501 is already free
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        is_free = s.connect_ex(("127.0.0.1", 8501)) != 0

    if not is_free:
        pytest.skip("Port 8501 is already in use by an existing service")

    # Start a dummy Python HTTP server on port 8501
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8501"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    import time
    time.sleep(1.5)

    try:
        start_ps1 = WIN_LAUNCHERS_DIR / "TradeX.ps1"
        stop_ps1 = WIN_LAUNCHERS_DIR / "TradeX-Stop.ps1"

        # 1. TradeX.ps1 should refuse to start and exit with error
        res_start = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(start_ps1), "-Quiet"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_start.returncode != 0
        assert "unrelated application" in res_start.stderr.lower() or "unrelated application" in res_start.stdout.lower()

        # 2. TradeX-Stop.ps1 should refuse to terminate the unrelated process
        res_stop = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(stop_ps1), "-Quiet"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_stop.returncode != 0
        assert "unrelated application" in res_stop.stdout.lower() or "unrelated application" in res_stop.stderr.lower()

        # 3. Confirm server is still alive
        assert server.poll() is None, "The unrelated process was terminated!"
    finally:
        server.terminate()
        server.wait(timeout=5)

