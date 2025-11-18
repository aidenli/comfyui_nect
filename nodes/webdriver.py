import asyncio
import threading
import json
import os
import sys
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any
import logging
from playwright.async_api import async_playwright, BrowserContext, Page
import shutil

# 配置日志格式
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(filename)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s'
)

# 与 Node 版本保持一致的尺寸预设
SIZE_PRESET = [
    "1:1",
    "智能",
    "21:9",
    "16:9",
    "3:2",
    "4:3",
    "3:4",
    "2:3",
    "9:16",
]

root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH: Optional[str] = None


def _normalize_viewport(viewport: Optional[Dict[str, Any]]) -> Optional[Dict[str, int]]:
    try:
        w = int(viewport.get("width")) if viewport and viewport.get("width") is not None else None
        h = int(viewport.get("height")) if viewport and viewport.get("height") is not None else None
        if w and h and w > 0 and h > 0:
            width = min(max(int(w), 320), 3840)
            height = min(max(int(h), 480), 2160)
            return {"width": width, "height": height}
    except Exception:
        pass
    return None


def _default_viewport() -> Dict[str, int]:
    return {"width": 1280, "height": 960}


async def _apply_stealth(context: BrowserContext):
    # 自定义规避脚本：隐藏 webdriver、设置语言/平台、WebGL 指纹、插件、chrome 对象等
    await context.add_init_script(
        script="""
        (() => {
          try {
            const proto = Navigator.prototype;
            // webdriver 为 undefined
            Object.defineProperty(proto, 'webdriver', { get: () => undefined });
            // 语言伪装
            Object.defineProperty(proto, 'languages', { get: () => ['zh-CN', 'zh'] });
            // 平台伪装
            Object.defineProperty(proto, 'platform', { get: () => 'Win32' });
            // 并发数与内存
            Object.defineProperty(proto, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(proto, 'deviceMemory', { get: () => 8 });
          } catch (e) {}

          try {
            // permissions.query 处理通知权限查询
            const orig = navigator.permissions && navigator.permissions.query;
            if (orig) {
              navigator.permissions.query = (params) => {
                if (params && params.name === 'notifications') {
                  return Promise.resolve({ state: Notification.permission });
                }
                return orig(params);
              };
            }
          } catch (e) {}

          try {
            // WebGL vendor / renderer 伪装
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(param) {
              const dbg = this.getExtension('WEBGL_debug_renderer_info');
              if (dbg) {
                if (param === dbg.UNMASKED_VENDOR_WEBGL) return 'Intel Inc.';
                if (param === dbg.UNMASKED_RENDERER_WEBGL) return 'Intel Iris OpenGL Engine';
              }
              return getParameter.call(this, param);
            };
          } catch (e) {}

          try {
            // plugins 伪装
            const fakePlugins = [
              { name: 'Chrome PDF Plugin' },
              { name: 'Chrome PDF Viewer' },
              { name: 'Native Client' }
            ];
            Object.defineProperty(navigator, 'plugins', { get: () => fakePlugins });
          } catch (e) {}

          try {
            // window.chrome 伪装
            Object.defineProperty(window, 'chrome', { get: () => ({ runtime: {} }) });
          } catch (e) {}
        })();
        """
    )


async def _launch_browser(state_json: str, headless: bool, viewport: Optional[Dict[str, int]]):
    global STATE_PATH
    state_dir = os.path.join(root_path, "state")
    os.makedirs(state_dir, exist_ok=True)
    STATE_PATH = os.path.join(state_dir, state_json)
    if not os.path.exists(STATE_PATH):
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            f.write("{}")

    parsed_viewport = _normalize_viewport(viewport) or _default_viewport()

    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=WebRtcHideLocalIpsWithMdns",
            "--lang=zh-CN,zh",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certifcate-errors",
            "--ignore-certifcate-errors-spki-list",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "--no-proxy-server",
        ],
        ignore_default_args=['--enable-automation'],
    )

    context = await browser.new_context(
        viewport=parsed_viewport,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        permissions=["geolocation", "notifications"],
        device_scale_factor=1,
        is_mobile=False,
        has_touch=False,
        accept_downloads=True,
        storage_state=STATE_PATH,
    )

    await context.grant_permissions(["geolocation", "notifications"])

    # 应用伪装
    await _apply_stealth(context)

    page = await context.new_page()
    return p, page, context


async def _goto_by_url(page: Page, url: str):
    retries = 3
    while retries > 0:
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            break
        except Exception as err:
            retries -= 1
            if retries == 0:
                raise err
            logging.info(f"第 {3 - retries} 次跳转失败，{retries} 秒后重试...")
            await page.wait_for_timeout(1000 * retries)


async def _do_login():
    logging.info("请在打开的浏览器中完成登录操作...")
    p, page, context = await _launch_browser("state.json", headless=False, viewport=_default_viewport())
    try:
        await _goto_by_url(page, "https://jimeng.jianying.com/ai-tool/home")

        login_avatar = page.locator("div#Personal>>img").first
        await login_avatar.wait_for(timeout=600000)
        await context.storage_state(path=STATE_PATH)
        logging.info(f"登录状态已保存到: {STATE_PATH}")
        await context.close()
        await p.stop()
        return True
    except Exception as err:
        try:
            await context.close()
            await p.stop()
        except Exception:
            pass
        raise err


async def _generate_image(params: Dict[str, Any]):
    # params: { model, prompt, size, refs, clientViewport }
    p, page, context = await _launch_browser("state.json", headless=True, viewport=params.get("clientViewport"))
    try:
        logging.info("开始生成图片...")
        await _goto_by_url(page, "https://jimeng.jianying.com/ai-tool/generate?type=image")

        if page.url == "https://jimeng.jianying.com/ai-tool/home":
            logging.info("未登录")
            await context.close()
            await p.stop()
            return False

        # 关闭浮层
        try:
            await page.locator("span[class*='lv-modal-close-icon']").first.click(timeout=3000)
        except Exception:
            pass

        # 上传图片
        refs: List[str] = params.get("refs") or []
        if isinstance(refs, list) and len(refs) > 0:
            await page.set_input_files("input[type='file']", refs)

        await page.wait_for_timeout(int(asyncio.get_running_loop().time() % 2000) + 500)

        # 选择分辨率
        size_button = await page.query_selector("div[class*='toolbar-settings'] > button")
        if size_button:
            await size_button.click()

        # 等待随机时间，模拟人类操作
        await page.wait_for_timeout(500 + int(asyncio.get_running_loop().time() % 2000))

        # 点击尺寸项
        size_text = params.get("size")
        await page.click(f"div[class*='radio-content-']>span:has-text('{size_text}')")
        await page.wait_for_timeout(500 + int(asyncio.get_running_loop().time() % 2000))
        await page.click("div[class*='resolution-commercial-option-']:has-text('高清 2K')")

        # 等待随机时间，模拟人类操作
        await page.wait_for_timeout(500 + int(asyncio.get_running_loop().time() % 2000))
        if size_button:
            await size_button.click()

        # 填写 prompt
        await page.fill("textarea[class*='prompt-textarea-']", params.get("prompt") or "")

        # 等待随机时间，模拟人类操作
        await page.wait_for_timeout(500 + int(asyncio.get_running_loop().time() % 2000))

        # 点击生成按钮
        generate_btn = await page.query_selector("div[class*='toolbar-']>>button[class*='submit-button-']")
        if generate_btn:
            await generate_btn.click()

        await page.wait_for_timeout(10000)

        # 等待图片生成
        logging.info("查找responsive-container")
        container = page.locator("div[class*='responsive-container']").first
        await container.wait_for(state="visible", timeout=300000)
        
        error_tips = container.locator("div[class*='error-tips-']").first
        img_first = container.locator("div[class*='record-box-wrapper-'] >> img").first

        # 等待失败提示或第一张图片出现（谁先出现就返回）
        try:
            wait_tasks = [
                asyncio.create_task(error_tips.wait_for(state="visible", timeout=300000)),
                asyncio.create_task(img_first.wait_for(state="visible", timeout=300000)),
            ]
            done, pending = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)
            # 取消未完成的等待，避免资源泄露
            for t in pending:
                t.cancel()
        except Exception:
            # 任一等待失败不影响后续判断
            pass

        if await error_tips.is_visible():
            logging.info("生成失败")
            await _set_response({
                "errcode": 1,
                "errmsg": "生成失败:" + (await error_tips.text_content() or "")
            })
            await context.close()
            await p.stop()
            return True

        img_list = container.locator("div[class*='record-box-wrapper-'] >> img")
        count = await img_list.count()
        logging.info(f"图片数量: {count}")

        downloads_dir = os.path.join(root_path, "downloads")
        if os.path.exists(downloads_dir):
            # 清空
            for root, dirs, files in os.walk(downloads_dir, topdown=False):
                for f in files:
                    try:
                        os.remove(os.path.join(root, f))
                    except Exception:
                        pass
                for d in dirs:
                    try:
                        os.rmdir(os.path.join(root, d))
                    except Exception:
                        pass
        os.makedirs(downloads_dir, exist_ok=True)

        save_paths: List[str] = []
        for i in range(count):
            attempt = 0
            success = False
            save_path = ""
            while attempt < 5 and not success:
                try:
                    img = img_list.nth(i)
                    logging.info(f"点击图片 {i + 1}")
                    await img.click(button="right")
                    await page.wait_for_timeout(1000)
                    # 期待下载事件
                    async with page.expect_download(timeout=10000) as dl_info:
                        await page.locator("div:text('下载图片')").first.click()
                    download = await dl_info.value
                    suggested = download.suggested_filename
                    save_path = os.path.join(downloads_dir, suggested)
                    await download.save_as(save_path)
                    await page.wait_for_timeout(1000)
                    success = True
                except Exception as err:
                    logging.info(f"图片 {i + 1} 第{attempt + 1}次下载失败: {getattr(err, 'message', str(err))}")
                    await page.wait_for_timeout(2000)
                attempt += 1

            if not success:
                logging.info(f"图片 {i + 1} 下载失败，已跳过")
            else:
                save_paths.append(save_path)
                logging.info(f"图片 {i + 1} 下载完成: {save_path}")

        await context.storage_state(path=STATE_PATH)

        await _set_response({
            "errcode": 0,
            "errmsg": "success",
            "data": {"imageList": save_paths},
        })
        await context.close()
        await p.stop()
        return True
    except Exception as err:
        try:
            await context.close()
            await p.stop()
        except Exception:
            pass
        raise err

async def _set_response(response: Dict[str, Any]):
    data = json.dumps({
        "errcode": response.get("errcode", 0),
        "errmsg": response.get("errmsg", "success"),
        "data": response.get("data", {}),
    }, ensure_ascii=False)
    logging.info(data)
    print(data)


def _compose_client_viewport(client_width: Optional[int], client_height: Optional[int]) -> Optional[Dict[str, int]]:
    if isinstance(client_width, int) and isinstance(client_height, int):
        return {"width": client_width, "height": client_height}
    return None


async def generate_image_func(
    model: str = "图片 4.0",
    prompt: str = "1girl",
    size: str = "9:16",
    refs: Optional[List[str]] = None,
    client_width: Optional[int] = None,
    client_height: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        if size not in SIZE_PRESET:
            logging.info("分辨率参数错误")
            return {"errcode": 1, "errmsg": "分辨率参数错误"}

        prompt_text = (prompt if isinstance(prompt, str) else str(prompt or ""))[:450]
        refs_input: List[str] = []
        if isinstance(refs, list):
            refs_input = [r for r in refs if isinstance(r, str) and os.path.exists(r)][:3]

        client_viewport = _compose_client_viewport(client_width, client_height)

        ok = await _generate_image({
            "model": model,
            "prompt": prompt_text,
            "size": size,
            "refs": refs_input,
            "clientViewport": client_viewport,
        })

        if not ok:
            await _do_login()
            ok = await _generate_image({
                "model": model,
                "prompt": prompt_text,
                "size": size,
                "refs": refs_input,
                "clientViewport": client_viewport,
            })

        downloads_dir = os.path.join(root_path, "downloads")
        image_list = [os.path.join(downloads_dir, f) for f in os.listdir(downloads_dir)] if os.path.exists(downloads_dir) else []

        if len(image_list) == 0:
            logging.info("生成失败或超时")
            return {"errcode": 1, "errmsg": "生成失败或超时"}

        return {"errcode": 0, "errmsg": "success", "data": {"imageList": image_list}}
    except Exception as error:
        stack = traceback.format_exc()
        logging.info(getattr(error, "message", str(error)) or "生成异常", stack)
        return {"errcode": 1, "errmsg": getattr(error, "message", str(error)) or "生成异常"}


def _run_async_blocking(coro: "asyncio.coroutines"):
    """在已有事件循环环境下，安全同步执行协程。
    - 若当前没有运行中的事件循环，直接使用 asyncio.run
    - 若已有事件循环（例如在 ComfyUI 内部），则在独立线程中创建事件循环并运行
    """
    try:
        asyncio.get_running_loop()
        loop_running = True
    except RuntimeError:
        loop_running = False

    if not loop_running:
        return asyncio.run(coro)

    result_holder = {}
    exc_holder = {}

    def runner():
        try:
            result_holder["value"] = asyncio.run(coro)
        except Exception as e:
            exc_holder["error"] = e

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join()

    if "error" in exc_holder:
        raise exc_holder["error"]
    return result_holder.get("value")


def generate_image(
    model: str = "图片 4.0",
    prompt: str = "1girl",
    size: str = "9:16",
    refs: Optional[List[str]] = None,
    client_width: Optional[int] = None,
    client_height: Optional[int] = None,
) -> Dict[str, Any]:
    # 清空ref和downloads目录（若传入了refs则不清空refs目录，避免删掉输入图片）
    try:
        downloads_dir = os.path.join(root_path, "downloads")
        if os.path.exists(downloads_dir):
            shutil.rmtree(downloads_dir, ignore_errors=True)
        os.makedirs(downloads_dir, exist_ok=True)

        if not refs:
            refs_dir = os.path.join(root_path, "refs")
            if os.path.exists(refs_dir):
                shutil.rmtree(refs_dir, ignore_errors=True)
            os.makedirs(refs_dir, exist_ok=True)
    except Exception:
        # 清理目录失败不影响后续生成流程
        pass

    return _run_async_blocking(generate_image_func(model, prompt, size, refs, client_width, client_height))


def login():
    """同步封装登录流程"""
    return _run_async_blocking(_do_login())


async def _cli_main(argv: List[str]):
    import argparse
    parser = argparse.ArgumentParser(description="Nect CLI (Python版)")
    parser.add_argument("--model", "-m", default="图片 4.0")
    parser.add_argument("--prompt", "-p", default="咖啡屋街边平台，吧台桌椅，绿植鲜花，香薰蜡烛，户外灯X石砌地面的小巷，一侧是老旧的咖啡屋。桌面山热咖啡，小蛋糕，悬挂着一盏亮起的古朴灯笼")
    parser.add_argument("--size", "-s", default="9:16")
    parser.add_argument("--refs", "-r", default="", help="引用图片列表(JSON数组)")
    # 去掉服务模式，仅保留命令行生成
    args = parser.parse_args(argv)

    try:
        if args.size not in SIZE_PRESET:
            raise ValueError("分辨率参数错误")

        refs: List[str] = []
        if args.refs:
            try:
                refs = json.loads(args.refs)
            except Exception:
                refs = []
        refs = [r for r in refs if os.path.exists(r)][:3]

        prompt_text = (args.prompt if isinstance(args.prompt, str) else str(args.prompt or ""))[:450]

        result = await generate_image_func(
            model=args.model,
            prompt=prompt_text,
            size=args.size,
            refs=refs,
            client_width=None,
            client_height=None,
        )
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        await _set_response({"errcode": 1, "errmsg": getattr(error, "message", str(error))})


def main():
    # CLI 入口
    argv = sys.argv[1:]
    asyncio.run(_cli_main(argv))


if __name__ == "__main__":
    main()