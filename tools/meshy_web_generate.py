#!/usr/bin/env python3
"""Drive Meshy's logged-in Firefox web UI for Smart Topology image-to-3D generation."""

import argparse, configparser, json, os, re, shutil, sys, time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options

MESHY_URL = "https://www.meshy.ai/workspace"
DOWNLOAD_MIMES = "application/octet-stream,model/gltf-binary,model/gltf+json,application/zip,application/x-zip-compressed"

def discover_firefox_profile() -> Path:
    ini = Path.home() / ".mozilla/firefox/profiles.ini"
    cp = configparser.RawConfigParser()
    cp.read(ini)
    candidates = []
    for sec in cp.sections():
        if not sec.startswith("Profile"): continue
        raw = cp.get(sec, "Path", fallback="")
        if not raw: continue
        rel = cp.get(sec, "IsRelative", fallback="1") == "1"
        profile = (ini.parent / raw) if rel else Path(raw)
        score = 0
        if cp.get(sec, "Default", fallback="0") == "1": score += 10
        if "release" in cp.get(sec, "Name", fallback="").lower(): score += 5
        if (profile / "cookies.sqlite").exists(): score += 3
        if (profile / "storage").exists(): score += 2
        candidates.append((score, profile))
    candidates.sort(reverse=True)
    return candidates[0][1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", nargs=4, required=True, help="4 reference images: front right back front_three_quarter")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--target-polycount", type=int, default=20000, help="Smart Topology target polycount")
    parser.add_argument("--max-minutes", type=float, default=30.0)
    args = parser.parse_args()

    images = [Path(p).expanduser().resolve() for p in args.images]
    for p in images:
        if not p.exists():
            raise SystemExit(f"Missing: {p}")
    out = Path(args.out).expanduser().resolve()
    download_dir = out / "downloads"
    profile_copy = out / "profile_copy"
    out.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)

    source = discover_firefox_profile()
    shutil.copytree(source, profile_copy, ignore=lambda d, n: set(x for x in n if x.lower() in {"lock", ".parentlock", "parent.lock"} or "cache" in x.lower()))

    opts = Options()
    opts.add_argument("-profile"); opts.add_argument(str(profile_copy))
    opts.add_argument("-headless")
    opts.set_preference("browser.download.folderList", 2)
    opts.set_preference("browser.download.dir", str(download_dir))
    opts.set_preference("browser.download.useDownloadDir", True)
    opts.set_preference("browser.helperApps.neverAsk.saveToDisk", DOWNLOAD_MIMES)
    opts.set_preference("pdfjs.disabled", True)

    driver = webdriver.Firefox(options=opts)
    driver.set_window_size(1600, 1200)
    driver.set_page_load_timeout(90)
    wait = WebDriverWait(driver, 15)

    try:
        driver.get(MESHY_URL)
        time.sleep(5)

        # Verify logged in
        body = driver.find_element(By.TAG_NAME, "body").text
        if "Log In" in body[:500] and "7,911" not in body[:2000]:
            raise RuntimeError("Not logged into Meshy")

        # Select Smart Topology (value="lowpoly")
        st = driver.find_element(By.CSS_SELECTOR, 'input[type=radio][value="lowpoly"]')
        driver.execute_script("arguments[0].click()", st)
        time.sleep(1)

        # Enable Multi-view (3rd switch)
        switches = driver.find_elements(By.CSS_SELECTOR, '[role="switch"]')
        if len(switches) >= 2:
            driver.execute_script("arguments[0].click()", switches[1])  # Multi-view
        time.sleep(0.5)

        # Enable Pose (4th switch) then select T-Pose
        if len(switches) >= 3:
            driver.execute_script("arguments[0].click()", switches[2])  # Pose
        time.sleep(0.5)
        tpose = driver.find_element(By.CSS_SELECTOR, 'input[type=radio][value="t"]')
        driver.execute_script("arguments[0].click()", tpose)
        time.sleep(0.5)

        # Set target polycount
        try:
            poly_input = driver.find_element(By.CSS_SELECTOR, 'input[type=number], input[aria-label*="poly"], input[aria-label*="count"]')
            poly_input.clear()
            poly_input.send_keys(str(args.target_polycount))
        except:
            pass

        # Upload images via drag-and-drop (multi-file input doesn't accept multiple)
        # Meshy multi-view mode uses a drop zone that accepts multiple files
        drop_zone = driver.execute_script("""
            // Find the drop zone - it's the click/drag area with the upload prompt
            const dz = document.querySelector('[class*="upload"], [class*="drop"], [class*="drag"], [class*="Upload"]');
            if (dz) return {found: true, tag: dz.tagName, cls: dz.className};
            // Fallback: use the tabpanel body
            const panel = document.querySelector('[role="tabpanel"]');
            if (panel) return {found: true, tag: panel.tagName, cls: panel.className};
            return {found: false};
        """)
        
        # Create a DataTransfer with the files and dispatch drop event
        driver.execute_script("""
            const images = arguments[0];
            const dt = new DataTransfer();
            // We need to create File objects from the paths - Selenium can't do this directly
            // Instead, find the file input, make it accept multiple, and use it
            const input = document.querySelector('input[type=file]');
            if (input) {
                input.removeAttribute('multiple');
                input.setAttribute('multiple', '');
            }
        """, [str(p) for p in images])
        
        # Upload one at a time, re-locating input each time (DOM refreshes after each upload)
        for img in images:
            try:
                fi = driver.find_element(By.CSS_SELECTOR, 'input[type=file]')
                driver.execute_script("arguments[0].setAttribute('multiple', 'true'); arguments[0].style.display='block'; arguments[0].style.opacity='1'", fi)
                fi.send_keys(str(img))
                time.sleep(3)
            except Exception as e:
                print(f"Upload retry: {e}")
                time.sleep(2)
                fi = driver.find_element(By.CSS_SELECTOR, 'input[type=file]')
                driver.execute_script("arguments[0].setAttribute('multiple', 'true'); arguments[0].style.display='block'; arguments[0].style.opacity='1'", fi)
                fi.send_keys(str(img))
                time.sleep(3)
        time.sleep(5)

        # Click Generate
        gen_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Generate')]")
        # Use the first visible Generate button (tabpanel one, not sidebar one)
        gen_btns = driver.find_elements(By.XPATH, "//button[contains(text(),'Generate')]")
        for btn in gen_btns:
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                break
        time.sleep(5)

        # Wait for completion
        started = time.time()
        while time.time() - started < args.max_minutes * 60:
            time.sleep(15)
            body_text = driver.find_element(By.TAG_NAME, "body").text
            # Check for download buttons or completion indicators
            if any(w in body_text for w in ["Download", ".glb", ".fbx"]):
                # Try clicking download
                dl_btns = driver.find_elements(By.XPATH, "//button[contains(text(),'Download')]")
                for btn in dl_btns:
                    if btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        time.sleep(10)
                        break
                # Check for downloaded files
                files = list(download_dir.rglob("*"))
                glbs = [f for f in files if f.suffix == '.glb' and f.stat().st_size > 100000]
                if glbs:
                    glb = max(glbs, key=lambda f: f.stat().st_mtime)
                    result = {"ok": True, "glb": str(glb), "size": glb.stat().st_size, "out": str(out)}
                    (out / "result.json").write_text(json.dumps(result, indent=2))
                    print(json.dumps(result, indent=2))
                    return 0

        # Timeout
        result = {"ok": False, "error": "timeout", "out": str(out), "downloaded_files": [str(f) for f in download_dir.rglob("*") if f.is_file()]}
        (out / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return 2

    except Exception as e:
        result = {"ok": False, "error": type(e).__name__, "message": str(e)[:500], "out": str(out)}
        (out / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return 1
    finally:
        try: driver.quit()
        except: pass
        if profile_copy.exists():
            shutil.rmtree(profile_copy)

if __name__ == "__main__":
    raise SystemExit(main())
