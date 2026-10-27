"""Offline browser screenshots; requires pip install playwright and system Chrome."""
import os
import re
import socket
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]


def main():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        port = s.getsockname()[1]
    env = dict(os.environ, NARRATE_UI_MOCK_ONLY='1', GRADIO_ANALYTICS_ENABLED='False', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    process = subprocess.Popen([sys.executable,'-m','app.app','--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    url = f'http://127.0.0.1:{port}'
    assets = ROOT/'blog-assets'
    assets.mkdir(exist_ok=True)
    numbers = [int(m[1]) for f in assets.iterdir() if (m:=re.match(r'^(\d+)_',f.name))]
    number = max(numbers,default=0)+1
    try:
        for _ in range(120):
            try:
                with urlopen(url,timeout=1) as response:
                    if response.status == 200: break
            except OSError:
                time.sleep(.5)
        else:
            raise RuntimeError('UI did not start')
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-background-networking','--disable-component-update','--renderer-process-limit=1'])
            page = browser.new_page(viewport={'width':1280,'height':900})
            # The app needs only loopback assets; deny all external browser requests.
            page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(url) else route.abort())
            page.goto(url)
            page.locator('.badge').first.wait_for()  # MOCK, NVIDIA DEV or Nebius cached runs
            page.wait_for_timeout(1000)
            for offset, name in enumerate(('samples','trace')):
                if name == 'trace':
                    page.locator('#agent-trace').scroll_into_view_if_needed()
                    page.locator('.trace-scroll').evaluate('(el) => el.scrollTop = 1050')
                target = assets/f'{number+offset:02}_{date.today().isoformat()}_ui_{name}.png'
                page.screenshot(path=str(target))
                print(target.relative_to(ROOT))
            # Check keyboard-accessible controls and the picture-hiding toggle.
            page.get_by_label('Eyes closed · hear audio only').check()
            page.wait_for_function('document.querySelector("#sample-media").classList.contains("eyes-closed")')
            page.get_by_role('tab',name='Run · live').click()
            page.get_by_role('button',name='Run agent',exact=True).wait_for()
            page.get_by_role('tab',name='Samples · zero cost').click()
            page.set_viewport_size({'width':1280,'height':720})
            page.evaluate('window.scrollTo(0,0)')
            assert page.locator('#agent-trace').bounding_box()['y'] < 650
            page.get_by_role('tab',name='Run · live').click()
            page.locator('input[type=file]').first.set_input_files(str(ROOT/'samples/sample_kitchen.mp4'))
            page.get_by_text('sample_kitchen.mp4',exact=False).last.wait_for()
            page.wait_for_timeout(1000)
            page.get_by_role('button',name='Run agent',exact=True).click()
            page.get_by_text('MOCK · offline / zero cost',exact=True).last.wait_for(timeout=120000)
            page.get_by_text('Download results',exact=True).wait_for()
            assert page.locator('video').last.get_attribute('src') or page.locator('video source').count()
            assert page.request.get(url+'/docs/readme').status == 200
            assert page.request.get(url+'/docs/sources').status == 200
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=15)

if __name__ == '__main__':
    main()
