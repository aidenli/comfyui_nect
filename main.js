import { chromium } from "playwright-extra";
import stealth from "puppeteer-extra-plugin-stealth";
import path from "path";
import fs from "fs";
import yargs from "yargs";
import { hideBin } from "yargs/helpers";
import { fileURLToPath } from "url";
import express from "express";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 初始化 stealth 插件
chromium.use(stealth());

// Add the stealth plugin to playwright-extra
chromium.use(stealth);

const SIZE_PRESET = [
    "1:1",
    "智能",
    "21:9",
    "16:9",
    "3:2",
    "4:3",
    "3:4",
    "2:3",
    "9:16",
];

let STATE_PATH; // 状态保存文件

function normalizeViewport(viewport) {
    try {
        const w = Number(viewport?.width);
        const h = Number(viewport?.height);
        if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) {
            // 设定合理的上下限，避免异常值
            const width = Math.min(Math.max(Math.floor(w), 320), 3840);
            const height = Math.min(Math.max(Math.floor(h), 480), 2160);
            return { width, height };
        }
    } catch (_) {}
    return null;
}

function getDefaultViewport() {
    // 默认分辨率：在桌面环境下较稳定
    return { width: 1400, height: 720 };
}

async function launchBrowser(stateJson, headless, viewport) {
    STATE_PATH = path.join(__dirname, "state", stateJson);
    if (!fs.existsSync(STATE_PATH)) {
        // 创建文件
        fs.writeFileSync(STATE_PATH, "{}");
    }

    const browser = await chromium.launch({
        headless: headless,
        // headless: false,
        args: [
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
        ignoreDefaultArgs: ["--enable-automation"],
    });

    const parsedViewport = normalizeViewport(viewport) || getDefaultViewport();
    const context = await browser.newContext({
        viewport: parsedViewport,
        // viewport: { width: 1080, height: 720 },
        userAgent:
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        locale: "zh-CN",
        timezoneId: "Asia/Shanghai",
        permissions: ["geolocation", "notifications"],
        geolocation: { latitude: 22.5431, longitude: 114.0579 },
        deviceScaleFactor: 1,
        isMobile: false,
        hasTouch: false,
        acceptDownloads: true,
        storageState: STATE_PATH,
    });

    await context.grantPermissions(["geolocation", "notifications"]);

    const page = await context.newPage();
    return { page, context };
}

async function gotoByUrl(page, url) {
    let retries = 3;
    while (retries > 0) {
        try {
            await page.goto(url, {
                waitUntil: "networkidle",
                timeout: 60000,
            });
            break; // 成功则跳出循环
        } catch (err) {
            retries--;
            if (retries === 0) throw err; // 三次都失败则抛出异常
            writeLogs(`第 ${3 - retries} 次跳转失败，${retries} 秒后重试...`);
            await page.waitForTimeout(1000 * retries); // 指数退避
        }
    }
}

async function doLogin() {
    console.log("请在打开的浏览器中完成登录操作...");
    // 打开有头浏览器进行登录
    const { page, context } = await launchBrowser("state.json", false, getDefaultViewport());
    try {
        await gotoByUrl(page, "https://jimeng.jianying.com/ai-tool/home");

        // 查找id为Personal的div下的图片
        const loginAvatar = await page.locator("div#Personal>>img").first();
        await loginAvatar.waitFor({ timeout: 600000 });
        // 保存登录状态（Cookie + localStorage）
        await context.storageState({ path: STATE_PATH });
        writeLogs(`登录状态已保存到: ${STATE_PATH}`);
        console.log("登录成功");
        // 关闭浏览器
        await context.close();
    } catch (err) {
        if (context) {
            await context.close();
        }
        throw err
    }
}

async function generateImage(
    params = { model: "图片 4.0", prompt: "1girl", size: "9:16", refs: [], clientViewport: null }
) {
    const { page, context } = await launchBrowser("state.json", true, params.clientViewport);
    try {
        writeLogs("开始生成图片...");
        await gotoByUrl(
            page,
            "https://jimeng.jianying.com/ai-tool/generate?type=image"
        );


        const url = await page.url();
        if (url === "https://jimeng.jianying.com/ai-tool/home") {
            writeLogs("未登录");
            await context.close();
            return false;
        }

        // 关闭浮层
        try {
            await page.locator(`span[class*="lv-modal-close-icon"]`).first().click({ timeout: 3000 });
        } catch (err) {console.error("关闭浮层失败", err)}

        // 上传图片
        if (params.refs.length > 0) {
            await page.setInputFiles('input[type="file"]', params.refs);
        }

        // 选择分辨率
        // 获取元素 div，模糊匹配类名toolbar-settings 下的 button
        const sizeButton = await page.$("div[class*='toolbar-settings'] > button");
        await sizeButton.click();

        // 等待随机时间，模拟人类操作
        await page.waitForTimeout(Math.random() * 2000 + 500);

        // 点击 span，内容为 generateTypePreset.image.size.default
        await page.click(
            `div[class*="radio-content-"]>span:text("${params.size}")`
        );
        await page.waitForTimeout(Math.random() * 2000 + 500);
        await page.click(
            `div[class*="resolution-commercial-option-"]:has-text("高清 2K")`
        );

        // 等待随机时间，模拟人类操作
        await page.waitForTimeout(Math.random() * 2000 + 500);
        await sizeButton.click();

        // 模糊匹配className为prompt-textarea-的textarea
        await page.fill('textarea[class*="prompt-textarea-"]', params.prompt);

        // 等待随机时间，模拟人类操作
        await page.waitForTimeout(Math.random() * 2000 + 500);

        // 点击生成按钮
        const generateButton = await page.$(
            'div[class*="toolbar-"]>>button[class*="submit-button-"]'
        );
        await generateButton.click();

        // 等待随机时间，模拟人类操作
        await page.waitForTimeout(1000);

        // ------------------------- 等待图片生成 -------------------------

        writeLogs("查找responsive-container");
        const container = await page
            .locator("div[class*='responsive-container']")
            .first();
        await container.waitFor({ timeout: 5000 });

        const errorTips = await container.locator("div[class*='error-tips-']").first();
        const imgFirst = await container
            .locator("div[class*='record-box-wrapper-'] >> img")
            .first();

        await Promise.race([
            errorTips.waitFor({ timeout: 300000 }),
            imgFirst.waitFor({ timeout: 300000 })
        ]);

        if (await errorTips.isVisible()) {
            writeLogs("生成失败");
            setResponse({
                errcode: 1,
                errmsg: "生成失败:" + await errorTips.textContent()
            });
            await context.close();
            return true;
        }

        const imgList = await container.locator(
            "div[class*='record-box-wrapper-'] >> img"
        );
        const imgCount = await imgList.count();
        writeLogs(`图片数量: ${imgCount}`);
        // 清空下载目录
        const downloadsDir = path.join(__dirname, "downloads");
        if (fs.existsSync(downloadsDir)) {
            fs.rmSync(downloadsDir, { recursive: true });
        }
        fs.mkdirSync(downloadsDir);

        const savePathList = [];
        for (let i = 0; i < imgCount; i++) {
            let attempt = 0;
            let success = false;
            let savePath = '';
            while (attempt < 5 && !success) {
                try {
                    const img = await imgList.nth(i);
                    await img.click({ button: "right" });
                    await page.waitForTimeout(1000);
                    const downloadPromise = page.waitForEvent("download", { timeout: 10000 });
                    await page.locator('div:text("下载图片")').first().click();
                    const download = await downloadPromise;
                    savePath = path.join(downloadsDir, download.suggestedFilename());
                    await download.saveAs(savePath);
                    await page.waitForTimeout(1000);
                    success = true;
                } catch (err) {
                    writeLogs(`图片 ${i + 1} 第${attempt + 1}次下载失败: ${err?.message || err}`);
                    await page.waitForTimeout(1000);
                }
                attempt++;
            }

            if (!success) {
                writeLogs(`图片 ${i + 1} 下载失败，已跳过`);
            } else {
                savePathList.push(savePath);
                writeLogs(`图片 ${i + 1} 下载完成: ${savePath}`);
            }
        }

        await context.storageState({ path: STATE_PATH });

        setResponse({
            errcode: 0,
            errmsg: "success",
            data: {
                imageList: savePathList,
            },
        });
        await context.close();
        return true;
    } catch (err) {
        if (context) {
            await context.close();
        }
        throw err
    }
}

async function writeLogs(logs, stack = '') {
    const logsDir = path.join(__dirname, "logs");
    if (!fs.existsSync(logsDir)) {
        fs.mkdirSync(logsDir, { recursive: true });
    }

    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    const dateString = `${yyyy}-${mm}-${dd}`;

    const logFilePath = path.join(logsDir, `${dateString}_log.txt`);
    const stackErr = new Error().stack.split("\n");
    const callerLine = stackErr[3].trim();
    fs.appendFileSync(logFilePath, `${dateString} ${callerLine} ${logs}\nstack: ${stack}\n`);
}

async function setResponse(response = {}) {
    const data = JSON.stringify({
        errcode: response.errcode || 0,
        errmsg: response.errmsg || "success",
        data: response.data || {},
    })
    writeLogs(data);
    console.log(data);
}

async function startServer() {
    const app = express();
    app.use(express.json({ limit: '10mb' }));

    app.get('/health', (req, res) => {
        res.json({ ok: true });
    });

    app.post('/api/generate-image', async (req, res) => {
        try {
            res.setTimeout(300000);
            const { model = "图片 4.0", prompt = '1girl', size = '9:16', refs = [], clientWidth, clientHeight } = req.body || {};

            if (!SIZE_PRESET.includes(size)) {
                writeLogs('分辨率参数错误');
                return res.json({
                    errcode: 1,
                    errmsg: '分辨率参数错误',
                });
            }

            // 截取前450个字符，避免修改常量
            const promptText = (typeof prompt === 'string' ? prompt : String(prompt || '')).substring(0, 450);

            let refsInput = Array.isArray(refs) ? refs : [];
            refsInput = refsInput.filter((ref) => typeof ref === 'string' && fs.existsSync(ref)).slice(0, 3);

            const clientViewport = (function () {
                const wHeader = Number(req.headers['x-client-width']);
                const hHeader = Number(req.headers['x-client-height']);
                const wBody = Number(clientWidth);
                const hBody = Number(clientHeight);
                const w = Number.isFinite(wBody) ? wBody : (Number.isFinite(wHeader) ? wHeader : null);
                const h = Number.isFinite(hBody) ? hBody : (Number.isFinite(hHeader) ? hHeader : null);
                if (Number.isFinite(w) && Number.isFinite(h)) {
                    return { width: w, height: h };
                }
                return null;
            })();

            let ok = await generateImage({ model, prompt: promptText, size, refs: refsInput, clientViewport });

            if (!ok) {
                await doLogin();
                ok = await generateImage({ model, prompt: promptText, size, refs: refsInput, clientViewport });
            }

            const downloadsDir = path.join(__dirname, 'downloads');
            const imageList = fs.existsSync(downloadsDir)
                ? fs.readdirSync(downloadsDir).map((f) => path.join(downloadsDir, f))
                : [];

            if (imageList.length === 0) {
                writeLogs('生成失败或超时');
                return res.json({
                    errcode: 1,
                    errmsg: '生成失败或超时',
                });
            }

            return res.json({
                errcode: 0,
                errmsg: 'success',
                data: { imageList },
            });
        } catch (error) {
            // 获取error的堆栈
            const stack = error.stack || '';
            writeLogs(error.message || '生成异常', stack);
            return res.json({
                errcode: 1,
                errmsg: error.message || '生成异常',
            });
        }
    });

    const PORT = process.env.PORT || "11880";
    const server = app.listen(PORT, () => {
        console.log(`Server running at http://localhost:${PORT}/`);
    });
    server.setTimeout(300000);
}

/**
 * 主函数
 */
async function main() {
    // 获取命令行参数
    const argv = yargs(hideBin(process.argv))
        .command("--prompt <prompt> --size <size> --refs <引用图片列表>")
        .option("model", {
            alias: "m",
            type: "string",
            default: "图片 4.0",
            description: "模型名称",
        })
        .option("prompt", {
            alias: "p",
            type: "string",
            default: "1girl",
            description: "图片提示词",
        })
        .option("size", {
            alias: "s",
            type: "string",
            default: "9:16",
            description: "图片分辨率",
        })
        .option("refs", {
            alias: "r",
            type: "string",
            default: "",
            description: "引用图片列表(JSON数组)",
        })
        .parse();

    const sizePreset = SIZE_PRESET;

    try {
        if (!sizePreset.includes(argv.size)) {
            throw new Error("分辨率参数错误");
        }

        let refs = [];
        if (argv.refs) {
            refs = JSON.parse(argv.refs);
            // 检查文件是否存在
            refs = refs.filter((ref) => fs.existsSync(ref));
            // 取最多三张图片
            refs = refs.slice(0, 3);
        }

        // 截取前450个字符
        const promptText = (typeof argv.prompt === 'string' ? argv.prompt : String(argv.prompt || '')).substring(0, 450);

        const isLogin = await generateImage({
            model: argv.model,
            prompt: promptText,
            size: argv.size,
            refs,
        });

        if (!isLogin) {
            // 校验登录
            await doLogin();

            // 执行业务逻辑
            await generateImage({
                model: argv.model,
                prompt: promptText,
                size: argv.size,
                refs,
            });
        }
    } catch (error) {
        setResponse({
            errcode: 1,
            errmsg: error.message,
        });
    }
}

// 入口：命令行或服务模式
const argvRaw = hideBin(process.argv);
if (argvRaw.includes('--serve')) {
    startServer();
} else {
    main();
}

