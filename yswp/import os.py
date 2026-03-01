import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
# selenium相关导入
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# ===================== 配置项（无需修改，保留你的密码） =====================
TARGET_URL = "http://pc6688.uupan.net/"  # 目标网盘地址
FOLDER_PASSWORDS = {
    "/": "6688",  # 根目录【空间登录】密码
    "/游戏资源区一": "2626",
    "/游戏资源区二": "2626",
    "/游戏资源区三": "2626",
    "/游戏资源区四": "2626",
    "/游戏资源区五": "2626",
    "/游戏资源区六": "2626",
    "/资源整合目录": "2626",
    "/战地系列": "2626",
    "/GTA系列": "2626",
    "/鬼泣系列": "2626",
    "/足球系列": "2626",
    "/拳皇系列": "2626",
    "/如龙系列": "2626",
    "/巫师系列": "2626",
    "/龙珠系列": "2626",
    "/地平线系列": "2626",
    "/马里奥系列": "2626",
    "/支持VR系列": "2626",
    "/战锤40K系列": "2626",
    "/全面战争系列": "2626",
    "/红色警戒系列": "2626",
    "/使命召唤系列": "2626",
    "/我的世界系列": "2626",
    "/帝国时代系列": "2626",
    "/火影忍者系列": "2626",
    "/古墓丽影系列": "2626",
    "/三国无双系列": "2626",
    "/刺客信条系列": "2626",
    "/生化危机系列": "2626",
    "/极品飞车系列": "2626",
    "/孤岛危机系列": "2626",
    "/模拟农场系列": "2626",
    "/黑暗之魂系列": "2626",
    "/孤岛惊魂系列": "2626",
    "/模拟人生系列": "2626",
    "/模拟火车系列": "2626",
    "/极限竞速系列": "2626",
    "/真人影游系列": "2626"
}
SAVE_BASE_DIR = "./ys_pan_backup"  # 本地备份根目录
RETRY_TIMES = 3  # 网络卡顿适配：元素定位失败重试次数
CHROMEDRIVER_PATH = "d:/yswp/chromedriver.exe"  # 本地驱动绝对路径
BROWSER_DOWNLOAD_DIR = os.path.abspath("./ys_pan_backup/_browser_downloads")
# 全局变量
root_window_handle = None  # 根目录窗口句柄（唯一）
session = requests.Session()
driver = None  # 全局驱动

# ===================== 浏览器配置：国内网优化+防卡顿 =====================
CHROME_OPTIONS = Options()
CHROME_OPTIONS.add_argument("--start-maximized")  # 窗口最大化
CHROME_OPTIONS.add_argument("--no-sandbox")
CHROME_OPTIONS.add_argument("--disable-dev-shm-usage")
CHROME_OPTIONS.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
CHROME_OPTIONS.add_experimental_option("excludeSwitches", ["enable-automation"])
CHROME_OPTIONS.add_experimental_option("useAutomationExtension", False)
CHROME_OPTIONS.add_experimental_option("prefs", {
    "download.default_directory": BROWSER_DOWNLOAD_DIR,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
})
CHROME_OPTIONS.add_argument("--blink-settings=imagesEnabled=false,videoEnabled=false")
CHROME_OPTIONS.add_argument("--disable-extensions")
CHROME_OPTIONS.add_argument("--disable-plugins")
CHROME_OPTIONS.add_argument("--page-load-timeout=60")

# ===================== 初始化：加载本地驱动+国内网请求配置（无外网请求） =====================
def init_env():
    """初始化本地驱动+请求会话，全程无需VPN"""
    global driver
    try:
        service = Service(executable_path=CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=CHROME_OPTIONS)
        print(f"✅ 本地驱动加载成功！路径：{CHROMEDRIVER_PATH}")
    except Exception as e:
        raise Exception(f"❌ 本地驱动加载失败！请检查：1. chromedriver.exe是否在脚本同目录 2. 驱动版本和Chrome一致 → {str(e)[:50]}")
    
    # 浏览器防反爬+超时配置
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.implicitly_wait(30)  # 全局等待30秒，适配国内网卡顿
    driver.set_page_load_timeout(60)
    
    # requests会话配置：国内网稳连接，增加重试
    session.keep_alive = True
    session.adapters.DEFAULT_RETRIES = 5
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Referer": TARGET_URL
    })
    os.makedirs(BROWSER_DOWNLOAD_DIR, exist_ok=True)
    print(f"✅ 环境初始化完成，适配国内网络，定位失败将重试{RETRY_TIMES}次")

# ===================== 工具函数：重试装饰器+Cookie同步+根目录切回【新增核心】 =====================
def retry_decorator(max_retry=RETRY_TIMES):
    """函数重试装饰器，适配网络卡顿导致的单次失败"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(max_retry):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == max_retry - 1:
                        raise e
                    print(f"⚠️ 第{i+1}次执行失败，重试中...（原因：{str(e)[:50]}）")
                    time.sleep(3)
                    switch_to_root()  # 重试前先切回根目录
                    driver.refresh()
                    time.sleep(5)
            return None
        return wrapper
    return decorator

def sync_browser_cookie():
    """同步Cookie，增加异常兜底"""
    try:
        browser_cookies = driver.get_cookies()
        for cookie in browser_cookies:
            session.cookies.set(cookie['name'], cookie['value'], domain=".uupan.net", path="/")
        # print(f"🍪 Cookie同步成功")  # 关闭冗余日志，避免刷屏
    except Exception as e:
        print(f"⚠️ Cookie同步失败（不影响核心操作）：{str(e)[:50]}")

def switch_to_root():
    """【核心新增】强制切回根目录窗口，确保定位文件夹始终在根目录"""
    global root_window_handle
    try:
        driver.switch_to.window(root_window_handle)
        print(f"✅ 已切回根目录页面")
    except Exception as e:
        print(f"⚠️ 切回根目录失败，重新打开根目录 → {str(e)[:30]}")
        driver.get(TARGET_URL)
        root_window_handle = driver.current_window_handle
        time.sleep(3)

def normalize_item_name(name):
    return (name or "").strip().strip("【】")

def get_dom_items_snapshot():
    """从当前页面提取可见条目快照：名称、bh、缩进、大小字段（有大小通常是文件）"""
    script = r"""
        const extRe = /\.(txt|zip|rar|7z|iso|exe|msi|apk|pdf|doc|docx|xls|xlsx|ppt|pptx|mp4|mkv|avi|mp3|flac|torrent)$/i;
        const anchors = Array.from(document.querySelectorAll('a'))
            .filter(a => {
                const cs = window.getComputedStyle(a);
                const rect = a.getBoundingClientRect();
                const visible = a.offsetParent !== null && cs.display !== 'none' && cs.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                if (!visible) return false;
                const txt = (a.innerText || '').trim();
                if (!txt) return false;
                const cls = a.className || '';
                const title = (a.getAttribute('title') || '').trim();
                const href = (a.getAttribute('href') || '').trim();
                const hasBh = !!a.getAttribute('data-bh');
                const likelyFile = title.includes('时间') || title.includes('点击查看') || title.includes('下载') || cls.includes('ml-1') || extRe.test(txt) || extRe.test(title) || href.toLowerCase().includes('download');
                const likelyFolder = cls.includes('outline-green-6') || hasBh;
                return likelyFile || likelyFolder;
            });
    return anchors.map((a, idx) => {
        const cs = window.getComputedStyle(a);
        const marginLeft = parseFloat(cs.marginLeft || '0') || 0;
        const paddingLeft = parseFloat(cs.paddingLeft || '0') || 0;
        let sizeText = '';
        const next = a.nextElementSibling;
        if (next && next.matches('span.green')) {
            sizeText = (next.innerText || '').trim();
        }
        return {
            index: idx,
            name: (a.innerText || '').trim(),
            bh: a.getAttribute('data-bh') || '',
            title: (a.getAttribute('title') || '').trim(),
            href: (a.getAttribute('href') || '').trim(),
            indent: marginLeft + paddingLeft,
            size_text: sizeText,
            is_file: !!sizeText
                || ((a.getAttribute('title') || '').includes('时间'))
                || ((a.getAttribute('title') || '').includes('点击查看'))
                || ((a.getAttribute('title') || '').includes('下载'))
                || ((a.className || '').includes('ml-1'))
                || extRe.test((a.innerText || '').trim())
                || extRe.test((a.getAttribute('title') || '').trim())
                || ((a.getAttribute('href') || '').toLowerCase().includes('download'))
        };
    });
    """
    try:
        items = driver.execute_script(script)
        return items if isinstance(items, list) else []
    except Exception:
        return []

def find_scoped_items(after_items, before_items, folder_name, folder_bh=None):
    """按目标文件夹作用域提取内容：优先用folder_bh定位，避免误抓根目录并列项"""
    target_idx = -1
    base_indent = 0.0

    if folder_bh:
        for i, item in enumerate(after_items):
            if item.get("bh") == folder_bh:
                target_idx = i
                break

    if target_idx < 0:
        target_name = normalize_item_name(folder_name)
        for i, item in enumerate(after_items):
            if normalize_item_name(item.get("name", "")) == target_name:
                target_idx = i
                break
    if target_idx < 0:
        return []

    base_indent = float(after_items[target_idx].get("indent", 0) or 0)

    # 第一优先：按缩进获取直属/子级可见项
    scoped = []
    for item in after_items[target_idx + 1:]:
        cur_indent = float(item.get("indent", 0) or 0)
        # 到达下一个同层/上层目录（有bh）时停止；无bh文件项允许同层继续收集
        if item.get("bh") and cur_indent <= base_indent:
            break
        if cur_indent > base_indent or bool(item.get("is_file")):
            scoped.append(item)
    if scoped:
        return scoped

    # 第二优先：展开前后差集（仅限目标项之后）
    before_bh_set = {x.get("bh") for x in before_items if x.get("bh")}
    diff_items = []
    for item in after_items[target_idx + 1:]:
        bh = item.get("bh")
        if bh and bh not in before_bh_set:
            diff_items.append(item)
    if diff_items:
        return diff_items

    return []

def find_folder_element_by_name(folder_name):
    """在当前页找到目标文件夹元素：同名时优先缩进更小（更靠上层）"""
    script = """
    const target = (arguments[0] || '').trim();
    const norm = (s) => (s || '').replace(/[【】]/g, '').trim();
    const anchors = Array.from(document.querySelectorAll('a.p-1.outline-green-6[data-bh], a.outline-green-6[data-bh], a[data-bh]'))
        .filter(a => {
            const cs = window.getComputedStyle(a);
            const rect = a.getBoundingClientRect();
            return a.offsetParent !== null && cs.display !== 'none' && cs.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        })
        .filter(a => norm(a.innerText) === target);
    if (!anchors.length) return null;
    anchors.sort((a, b) => {
        const ia = (parseFloat(getComputedStyle(a).marginLeft || '0') || 0) + (parseFloat(getComputedStyle(a).paddingLeft || '0') || 0);
        const ib = (parseFloat(getComputedStyle(b).marginLeft || '0') || 0) + (parseFloat(getComputedStyle(b).paddingLeft || '0') || 0);
        return ia - ib;
    });
    return anchors[0];
    """
    try:
        elem = driver.execute_script(script, folder_name)
        return elem
    except Exception:
        return None

def input_password_and_verify(password):
    """若出现密码框则输入并点击验证；若未出现则视为已解锁"""
    try:
        pwd_input = WebDriverWait(driver, 12).until(
            EC.visibility_of_element_located((By.XPATH, '//input[@type="password" or @name="pwd" or @id="pwd" or contains(@placeholder, "密码")]'))
        )
    except Exception:
        return False

    pwd_input.clear()
    pwd_input.send_keys(password)
    print(f"✅ 密码输入完成：{password}")
    time.sleep(1)

    clicked_verify = False
    try:
        verify_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, '//*[contains(text(),"验证") or @value="验证" or contains(text(),"确认") or @value="确认"]'))
        )
        driver.execute_script("arguments[0].click();", verify_btn)
        clicked_verify = True
        print("✅ 已点击验证按钮")
    except Exception:
        driver.execute_script("document.forms.length>0 && document.forms[0].submit();")
        print("✅ 未找到验证按钮，已表单提交（兜底）")

    if clicked_verify:
        time.sleep(0.2)  # 非阻塞微等待，避免验证后长时间卡住
    return True

def close_folder_in_root(folder_name):
    """处理完成后在根目录点击同名文件夹进行折叠关闭"""
    try:
        switch_to_root()
        time.sleep(1)
        folder_elem = find_folder_element_by_name(folder_name)
        if folder_elem:
            driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", folder_elem)
            time.sleep(2)
            print(f"📁 已关闭文件夹：{folder_name}")
    except Exception as e:
        print(f"⚠️ 关闭文件夹失败（不影响后续）：{folder_name} → {str(e)[:40]}")

def click_file_by_bh(file_bh):
    script = """
    function visible(el){
        if (!el) return false;
        const cs = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return el.offsetParent !== null && cs.display !== 'none' && cs.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
    }
    function clickDownloadIconNear(anchor){
        if (!anchor) return false;
        const container = anchor.closest('li, tr, .flex, .grid, div') || anchor.parentElement;
        const scopes = [container, anchor.parentElement, anchor.closest('li'), anchor.closest('tr'), document];
        for (const scope of scopes){
            if (!scope) continue;
            const icon = scope.querySelector('i.xzbt[title*="下载"], i[title*="下载"].xzbt, i.eva-download-outline, i[title*="点击下载"], i.q-icon.eva-download-outline');
            if (icon && visible(icon)) {
                icon.scrollIntoView({block: 'center'});
                icon.click();
                return true;
            }
        }
        return false;
    }

    const bh = arguments[0];
    const nodes = Array.from(document.querySelectorAll('a[data-bh]')).filter(a => {
        return a.getAttribute('data-bh') === bh && visible(a);
    });
    if (!nodes.length) return false;
    const anchor = nodes[0];
    if (clickDownloadIconNear(anchor)) return true;
    anchor.scrollIntoView({block: 'center'});
    anchor.click();
    return true;
    """
    try:
        return bool(driver.execute_script(script, file_bh))
    except Exception:
        return False

def click_file_by_name(file_name):
    script = """
    function visible(el){
        if (!el) return false;
        const cs = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return el.offsetParent !== null && cs.display !== 'none' && cs.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
    }
    function clickDownloadIconNear(anchor){
        if (!anchor) return false;
        const container = anchor.closest('li, tr, .flex, .grid, div') || anchor.parentElement;
        const scopes = [container, anchor.parentElement, anchor.closest('li'), anchor.closest('tr'), document];
        for (const scope of scopes){
            if (!scope) continue;
            const icon = scope.querySelector('i.xzbt[title*="下载"], i[title*="下载"].xzbt, i.eva-download-outline, i[title*="点击下载"], i.q-icon.eva-download-outline');
            if (icon && visible(icon)) {
                icon.scrollIntoView({block: 'center'});
                icon.click();
                return true;
            }
        }
        return false;
    }

    const target = (arguments[0] || '').trim();
    const norm = (s) => (s || '').replace(/[【】]/g, '').trim();
    const nodes = Array.from(document.querySelectorAll('a')).filter(a => {
        if (!visible(a)) return false;
        const txt = norm(a.innerText || '');
        if (!txt || txt !== norm(target)) return false;
        const title = (a.getAttribute('title') || '');
        const cls = a.className || '';
        return title.includes('时间') || cls.includes('ml-1');
    });
    if (!nodes.length) return false;
    const anchor = nodes[0];
    if (clickDownloadIconNear(anchor)) return true;
    anchor.scrollIntoView({block: 'center'});
    anchor.click();
    return true;
    """
    try:
        return bool(driver.execute_script(script, file_name))
    except Exception:
        return False

def download_file_via_selenium(file_bh, file_name):
    """完全使用Selenium触发下载动作（不等待单文件完成）"""
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", file_name)
    print(f"📥 点击下载：{safe_name}")

    handles_before = list(driver.window_handles)
    clicked = False
    if file_bh:
        clicked = click_file_by_bh(file_bh)
        if clicked:
            print("🖱️ 已触发下载动作（优先下载图标）")
    if not clicked:
        clicked = click_file_by_name(file_name)
        if clicked:
            print("🖱️ 已触发下载动作（按文件名定位后点下载图标/兜底点击）")
    if not clicked:
        raise Exception("当前页面未找到该文件节点（可能目录已折叠或文件锚点无data-bh）")

    # 处理可能弹出的新标签页
    time.sleep(1)
    handles_after = list(driver.window_handles)
    if len(handles_after) > len(handles_before):
        for h in handles_after:
            if h not in handles_before:
                try:
                    driver.switch_to.window(h)
                    time.sleep(1)
                    driver.close()
                except Exception:
                    pass
        driver.switch_to.window(root_window_handle)
    time.sleep(0.2)  # 轻微节流，避免站点短时间内丢点击
    print(f"✅ 已加入下载队列：{safe_name}")

# ===================== 核心函数：文件夹处理（国内网优化+重试+定位兜底） =====================
@retry_decorator(max_retry=RETRY_TIMES)
def get_folder_content(folder_path, folder_name):
    password = FOLDER_PASSWORDS.get(folder_path, "")
    if not password:
        print(f"⚠️ {folder_path}：未配置密码，跳过")
        return [], []
    print(f"\n========== 开始处理：{folder_path} ==========")
    print(f"🔑 使用密码：{password} | 国内网适配模式")

    # 1. 根目录处理：表单提交+稳加载
    if folder_path == "/":
        driver.get(TARGET_URL)
        global root_window_handle
        root_window_handle = driver.current_window_handle  # 保存根目录唯一窗口句柄
        time.sleep(5)  # 国内网延长初始加载
        sync_browser_cookie()
        # 定位密码框（兜底多种匹配）
        pwd_input = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, '//input[@type="password" or @name="pwd" or @id="pwd"]'))
        )
        pwd_input.clear()
        pwd_input.send_keys(password)
        print(f"✅ 根目录密码输入完成：{password}")
        time.sleep(3)
        # 表单提交（根目录无明确按钮，兜底方案）
        driver.execute_script("document.forms.length>0 && document.forms[0].submit();")
        print(f"✅ 根目录表单提交，等待5秒加载...")
        time.sleep(5)
        sync_browser_cookie()
        print("✅ 根目录登录完成")
        return [], []

    # 2. 子文件夹处理：根目录校验+定位+密码验证【优化：增加根目录校验】
    else:
        switch_to_root()  # 定位前先切回根目录【核心修复】
        time.sleep(3)
        before_items = get_dom_items_snapshot()
        print(f"🔍 根目录下定位文件夹：{folder_name}")

        folder_elem = find_folder_element_by_name(folder_name)
        if not folder_elem:
            raise Exception(f"未找到目标文件夹元素：{folder_name}")

        folder_bh = folder_elem.get_attribute("data-bh")

        driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", folder_elem)
        print(f"✅ 已点击文件夹：{folder_name}，尝试密码验证")
        time.sleep(2)
        sync_browser_cookie()

        password_prompted = input_password_and_verify(password)
        if password_prompted:
            print(f"🔓 {folder_name} 验证已提交，等待内容展开")
        else:
            print(f"ℹ️ 未检测到密码框，可能该文件夹已解锁")

        try:
            WebDriverWait(driver, 2).until(
                lambda d: len(get_dom_items_snapshot()) > len(before_items)
            )
        except Exception:
            time.sleep(0.8)
        sync_browser_cookie()

    # 3. 等待目录内容加载，适配国内网卡顿
    print(f"⌛ 等待{folder_name}内容加载...")
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CLASS_NAME, "outline-green-6"))
    )
    time.sleep(4)
    # 4. 解析文件夹/文件【修复：限定在当前目标文件夹范围内，不再全页误抓】
    sub_folders = []
    files = []

    after_items = get_dom_items_snapshot()
    scoped_items = find_scoped_items(after_items, before_items, folder_name, folder_bh)

    # 站点特性兜底：部分目录需要“验证后再点一次文件夹”才真正展开
    if not scoped_items:
        print(f"⚠️ 首次验证后未检测到内容，尝试二次点击展开：{folder_name}")
        folder_elem_retry = find_folder_element_by_name(folder_name)
        if folder_elem_retry:
            driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", folder_elem_retry)
            time.sleep(3)
            sync_browser_cookie()
            after_items_retry = get_dom_items_snapshot()
            scoped_items = find_scoped_items(after_items_retry, before_items, folder_name, folder_bh)

    if not scoped_items:
        all_now = get_dom_items_snapshot()
        print(f"🧪 调试：当前可见候选条目{len(all_now)}个，目标目录作用域条目0个")
        print(f"⚠️ {folder_name}：未找到任何文件/子文件夹")
        return [], []

    print(f"🧪 调试：{folder_name}作用域共{len(scoped_items)}项")

    # 遍历解析：优先按页面大小字段判断文件（比关键词更可靠）
    for item in scoped_items:
        item_name = normalize_item_name(item.get("name", ""))
        data_bh = item.get("bh")
        if item_name == normalize_item_name(folder_name):
            continue
        item_url = urljoin(TARGET_URL, f"?bh={data_bh}") if data_bh else ""

        is_file = bool(item.get("is_file"))
        if is_file:
            file_size = (item.get("size_text") or "").strip() or "未知大小"
            files.append((item_url, item_name, file_size, data_bh))
            print(f"📄 发现文件：{item_name} | 大小：{file_size}")
        else:
            if data_bh:
                sub_folders.append((item_url, item_name))
                print(f"🔍 发现子文件夹：{item_name}")

    if len(files) == 0 and len(scoped_items) > 0:
        sample = scoped_items[:8]
        print("🧪 调试：作用域样本（前8项）")
        for s in sample:
            print(f"   - name={normalize_item_name(s.get('name',''))} | bh={s.get('bh','')} | is_file={bool(s.get('is_file'))} | title={s.get('title','')[:18]}")
    
    # 核心日志：显示解析结果
    print(f"✅ {folder_name}解析完成 → 子文件夹{len(sub_folders)}个 | 可下载文件{len(files)}个")
    return sub_folders, files

# ===================== 递归爬取：核心修复【处理完子文件夹强制切回根目录】 =====================
def crawl_configured_folders_only():
    """只处理FOLDER_PASSWORDS中配置的文件夹：打开→验证→下载→关闭，不递归打开未配置目录"""
    try:
        get_folder_content("/", "根目录")  # 仅做根目录登录
    except Exception as e:
        print(f"❌ 根目录登录失败：{str(e)[:80]}")
        return

    configured_paths = [p for p in FOLDER_PASSWORDS.keys() if p != "/" and FOLDER_PASSWORDS.get(p)]
    configured_paths = sorted(configured_paths, key=lambda p: (p.count("/"), p))
    print(f"\n🎯 仅处理已配置密码的文件夹：共{len(configured_paths)}个")

    for folder_path in configured_paths:
        folder_name = folder_path.strip("/").split("/")[-1]
        print(f"\n➡️ 处理配置目录：{folder_path}")
        try:
            _, files = get_folder_content(folder_path, folder_name)
            if len(files) == 0:
                print(f"📭 {folder_name}：已打开并验证，但无可下载文件")
            else:
                print(f"🚀 开始下载{folder_name}的{len(files)}个文件...")
                for file_url, file_name, file_size, file_bh in files:
                    try:
                        download_file_via_selenium(file_bh, file_name)
                    except Exception as e:
                        print(f"❌ 文件下载失败，跳过：{file_name} → {str(e)[:60]}")
                        continue
                print(f"✅ {folder_name}：下载点击已全部触发，继续下一个目录")
        except Exception as e:
            print(f"❌ 文件夹处理失败，跳过：{folder_path} → {str(e)[:80]}")
        finally:
            close_folder_in_root(folder_name)
            time.sleep(1)

# ===================== 主程序：优雅启动+兜底退出 =====================
if __name__ == "__main__":
    print(f"🚀 永硕e盘备份脚本（本地驱动版·全程无需VPN）启动")
    print(f"📌 配置：本地驱动={CHROMEDRIVER_PATH} | 备份目录={os.path.abspath(SAVE_BASE_DIR)}")
    print(f"💻 正在初始化本地驱动+浏览器...\n")
    os.makedirs(SAVE_BASE_DIR, exist_ok=True)
    try:
        init_env()  # 初始化本地驱动（无外网）
        crawl_configured_folders_only()  # 仅处理配置目录
    except KeyboardInterrupt:
        print(f"\n⚠️ 脚本被手动终止")
    except Exception as e:
        print(f"\n❌ 脚本全局异常：{str(e)[:100]}")
    finally:
        # 优雅关闭浏览器，无论是否异常
        if driver:
            try:
                driver.quit()
                print(f"\n🗑️  浏览器已正常关闭")
            except:
                print(f"\n🗑️  浏览器已强制关闭")
        print(f"\n🎉 备份流程结束！所有成功下载的文件已保存至：{os.path.abspath(SAVE_BASE_DIR)}")