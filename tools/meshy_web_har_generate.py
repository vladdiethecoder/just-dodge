#!/usr/bin/env python3
"""Meshy web automation with HAR capture to derive exact API calls.
Uses selenium-wire to intercept all network requests.
Saves .har file and .mhtml page snapshot for analysis."""

import argparse, configparser, json, os, shutil, sys, time
from pathlib import Path
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options

MESHY_URL = "https://www.meshy.ai/workspace"

def discover_firefox_profile():
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
        candidates.append((score, profile))
    candidates.sort(reverse=True)
    return candidates[0][1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", nargs=4, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--target-polycount", type=int, default=20000)
    parser.add_argument("--max-minutes", type=float, default=30.0)
    args = parser.parse_args()

    images = [Path(p).expanduser().resolve() for p in args.images]
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
    opts.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/octet-stream,model/gltf-binary")

    sw_opts = {
        'enable_har': True,
        'har_dir': str(out),
    }
    driver = webdriver.Firefox(options=opts, seleniumwire_options=sw_opts)
    driver.set_window_size(1600, 1200)
    driver.set_page_load_timeout(90)

    try:
        driver.get(MESHY_URL)
        time.sleep(5)

        body = driver.find_element(By.TAG_NAME, "body").text
        print(f"MESHY: {'LOGGED IN' if 'Log In' not in body[:500] else 'NOT LOGGED IN'}")

        # Select Smart Topology
        st = driver.find_element(By.CSS_SELECTOR, 'input[type=radio][value="lowpoly"]')
        driver.execute_script("arguments[0].click()", st)
        time.sleep(1)

        # Multi-view ON
        switches = driver.find_elements(By.CSS_SELECTOR, '[role="switch"]')
        if len(switches) >= 2:
            driver.execute_script("arguments[0].click()", switches[1])
        time.sleep(0.5)

        # Pose ON → T-Pose
        if len(switches) >= 3:
            driver.execute_script("arguments[0].click()", switches[2])
        time.sleep(0.5)
        tpose = driver.find_element(By.CSS_SELECTOR, 'input[type=radio][value="t"]')
        driver.execute_script("arguments[0].click()", tpose)
        time.sleep(0.5)

        # Upload images one at a time
        for idx, img in enumerate(images):
            for attempt in range(3):
                try:
                    fi = driver.find_element(By.CSS_SELECTOR, 'input[type=file]')
                    driver.execute_script("arguments[0].style.display='block'; arguments[0].style.opacity='1'", fi)
                    fi.send_keys(str(img))
                    print(f"Uploaded {idx+1}/4: {img.name}")
                    time.sleep(3)
                    break
                except Exception as e:
                    print(f"Upload attempt {attempt+1} failed: {e}")
                    time.sleep(2)
        time.sleep(3)

        # Save MHTML snapshot
        mhtml_data = driver.execute_script("return document.documentElement.outerHTML")
        (out / "page_snapshot.html").write_text(mhtml_data)
        print(f"MHTML saved: {out / 'page_snapshot.html'}")

        # Click Generate
        gen_btns = driver.find_elements(By.XPATH, "//button[contains(text(),'Generate')]")
        for btn in gen_btns:
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                print("Clicked Generate")
                break
        time.sleep(5)

        # Wait for API calls to happen
        time.sleep(10)

        # Save HAR
        har_path = out / "network.har"
        with open(har_path, 'w') as f:
            f.write(driver.har)
        print(f"HAR saved: {har_path}")

        # Filter Meshy API calls
        api_calls = []
        for entry in json.loads(driver.har).get('log', {}).get('entries', []):
            req = entry.get('request', {})
            url = req.get('url', '')
            if 'meshy.ai' in url and '/api/' in url:
                api_calls.append({
                    'url': url,
                    'method': req.get('method'),
                    'status': entry.get('response', {}).get('status'),
                    'request_headers': {k: v for k, v in req.get('headers', {}).items() if k.lower() not in ('cookie', 'authorization')},
                })
        (out / "meshy_api_calls.json").write_text(json.dumps(api_calls, indent=2))
        print(f"Meshy API calls: {len(api_calls)}")

        # Wait for completion
        started = time.time()
        while time.time() - started < args.max_minutes * 60:
            time.sleep(15)
            body_text = driver.find_element(By.TAG_NAME, "body").text
            glbs = [f for f in download_dir.rglob("*.glb") if f.stat().st_size > 100000]
            if glbs:
                glb = max(glbs, key=lambda f: f.stat().st_mtime)
                result = {"ok": True, "glb": str(glb), "size": glb.stat().st_size, "out": str(out)}
                (out / "result.json").write_text(json.dumps(result, indent=2))
                print(json.dumps(result, indent=2))
                return 0

        result = {"ok": False, "error": "timeout", "out": str(out)}
        (out / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return 2

    except Exception as e:
        result = {"ok": False, "error": type(e).__name__, "message": str(e)[:500], "out": str(out)}
        (out / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return 1
    finally:
        # Save HAR even on failure
        try:
            har_path = out / "network.har"
            with open(har_path, 'w') as f:
                f.write(driver.har)
            print(f"HAR saved on exit: {har_path}")
        except: pass
        try: driver.quit()
        except: pass
        if profile_copy.exists():
            shutil.rmtree(profile_copy)

if __name__ == "__main__":
    raise SystemExit(main())
