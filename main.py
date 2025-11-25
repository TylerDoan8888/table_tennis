import logging
import time
import requests  # << THÊM IMPORT NÀY

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ================== CẤU HÌNH LOGGER ==================
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
# ======================================================

# ================== TELEGRAM CONFIG ==================
TELEGRAM_TOKEN = "7513782443:AAFrjqMeCEJ7NzC3m5RCwxZtqk9n0pyovKM"
CHAT_ID = "5559311100"

def send_telegram_message(text: str) -> None:
    """
    Gửi message tới Telegram sử dụng bot token + chat id.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": text
    }
    try:
        resp = requests.post(url, data=data, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"Telegram trả về lỗi {resp.status_code}: {resp.text}")
        else:
            logger.info("Đã gửi log lên Telegram.")
    except Exception as e:
        logger.warning(f"Lỗi khi gửi Telegram: {e}")
# =====================================================

# lưu danh sách trận đã gửi Telegram (theo cặp tên người chơi)
sent_matches = set()

def scroll_event_list_container(driver, steps: int = 5, step_size: int = 400, pause: float = 0.7):
    """
    Tìm container scroll bao quanh danh sách trận, rồi scroll nó xuống.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Lấy 1 element đại diện trong danh sách trận – dùng tên người chơi
    sample_elem = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((
            By.CSS_SELECTOR,
            "span.eventlist_asia_fe_EventCard_teamNameText"
        ))
    )

    # Dùng JS tìm ancestor có overflow-y: auto/scroll
    container = driver.execute_script("""
        let el = arguments[0];
        while (el) {
            const style = window.getComputedStyle(el);
            if (/(auto|scroll)/.test(style.overflowY)) {
                return el;
            }
            el = el.parentElement;
        }
        return null;
    """, sample_elem)

    if not container:
        # fallback: thử scroll window như cũ
        for i in range(steps):
            driver.execute_script(f"window.scrollBy(0, {step_size});")
            time.sleep(pause)
        return

    # Scroll chính cái container đó
    for i in range(steps):
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollTop + arguments[1];",
            container,
            step_size
        )
        time.sleep(pause)

# ======================================================

def check_and_notify_matches(driver):
    """
    Tìm các trận có tỉ số 1:2 hoặc 2:1.
    Nếu trận chưa gửi Telegram thì gửi và đánh dấu để lần sau không gửi lại.
    """
    global sent_matches

    try:
        logger.info("Đang tìm các trận có tỉ số 1:2 hoặc 2:1...")

        # Tìm tất cả score 1:2 hoặc 2:1 (bỏ khoảng trắng)
        score_elems = driver.find_elements(
            By.XPATH,
            (
                "//div[contains(@class,'eventlist_asia_fe_EventTime_scoreLive')"
                " and (translate(normalize-space(), ' ', '')='1:2'"
                "      or translate(normalize-space(), ' ', '')='2:1')]"
            )
        )

        logger.info(f"Tìm thấy {len(score_elems)} trận có tỉ số 1:2 hoặc 2:1.")

        new_sent = 0

        for idx, score_elem in enumerate(score_elems, start=1):
            try:
                # Lấy tỉ số hiển thị
                score_text = score_elem.text.strip()

                # Đi lên thẻ chứa cả trận (event card)
                event_card = score_elem.find_element(
                    By.XPATH,
                    "./ancestor::*[.//span[contains(@class,'eventlist_asia_fe_EventCard_teamNameText')]][1]"
                )

                # Lấy tên người chơi trong trận
                name_elems = event_card.find_elements(
                    By.CSS_SELECTOR,
                    "span.eventlist_asia_fe_EventCard_teamNameText"
                )

                player_names = [n.text.strip() for n in name_elems if n.text.strip()]

                if len(player_names) >= 2:
                    # tạo ID duy nhất cho trận dựa trên 2 tên
                    match_id = f"{player_names[0]}|{player_names[1]}"

                    if match_id in sent_matches:
                        logger.info(
                            f"Trận {idx}: {player_names[0]} vs {player_names[1]} – Tỉ số: {score_text} (đã gửi trước đó, bỏ qua)"
                        )
                        continue  # không gửi lại nữa

                    # trận mới -> log + gửi Telegram
                    message = (
                        f"TRẬN MỚI 1:2 / 2:1\n"
                        f"{player_names[0]} vs {player_names[1]}\n"
                        f"Tỉ số hiện tại: {score_text}"
                    )
                    logger.info(message)
                    send_telegram_message(message)

                    sent_matches.add(match_id)
                    new_sent += 1

                else:
                    logger.info(
                        f"Trận {idx}: (không đọc đủ tên người chơi) – Tỉ số: {score_text}"
                    )

            except Exception as inner_e:
                logger.warning(f"Lỗi khi xử lý 1 trận: {inner_e}")

        return new_sent

    except Exception as e:
        logger.warning(f"Lỗi khi tìm các trận có tỉ số 1:2 hoặc 2:1: {e}")
        return 0

# ======================================================

def main():
    url = (
        "https://prod20091.fxf774.com/vi/asian-view/live/"
        "B%C3%B3ng-b%C3%A0n?operatorToken=logout"
    )

    options = Options()
    options.add_argument("--start-maximized")

    logger.info("Khởi tạo Chrome WebDriver bằng ChromeDriverManager...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        logger.info(f"Mở trang: {url}")
        driver.get(url)

        time.sleep(3)

        # ================== ĐÓNG POPUP ==================
        try:
            logger.info("Đang tìm và đóng popup...")
            close_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    ".components-fe_Popup_iconClose.master_fe_ViewStyles_defaultCloseButton"
                ))
            )
            close_btn.click()
            logger.info("Popup đã được đóng.")
        except Exception as e:
            logger.warning(f"Không tìm thấy popup hoặc không thể đóng: {e}")
        # ==================================================

        # ================== CLICK 'LỰA CHỌN GIẢI ĐẤU' ============
        try:
            logger.info("Đang tìm nút 'Lựa chọn giải đấu'...")

            league_btn = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "button.eventlist_asia_fe_Header_selectLeagueBtnNotActive"
                ))
            )

            # Scroll
            driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                league_btn
            )
            time.sleep(1)

            # Hover
            ActionChains(driver).move_to_element(league_btn).perform()
            time.sleep(0.5)

            # Click
            league_btn.click()
            logger.info("Đã nhấn vào nút 'Lựa chọn giải đấu'.")

        except Exception as e:
            logger.warning(f"Không thể nhấn vào nút 'Lựa chọn giải đấu': {e}")

        # ==========================================================

        # ================== BỎ CHỌN TẤT CẢ ==================
        try:
            logger.info("Đang bỏ chọn tất cả giải đấu...")
            select_all_checkbox = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    "span.eventlist_asia_fe_SelectLeaguesModal_styledCheckboxSelectAll"
                ))
            )
            select_all_checkbox.click()
            logger.info("Đã bỏ chọn tất cả giải đấu.")
        except Exception as e:
            logger.warning(f"Không thể bỏ chọn tất cả giải đấu: {e}")
        # =====================================================

        # ================== CHỌN GIẢI SETKA CUP ==================
        try:
            logger.info("Đang tìm và chọn giải 'Giải Setka Cup'...")

            league_label = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((
                    By.XPATH,
                    "//span[contains(@class,'eventlist_asia_fe_SelectLeaguesModal_leagueName')"
                    " and normalize-space()='Giải Setka Cup']"
                ))
            )

            try:
                checkbox = league_label.find_element(
                    By.XPATH,
                    "./preceding-sibling::*[contains(@class,'SelectLeaguesModal_styledCheckbox') or contains(@class,'SelectLeaguesModal_check')][1]"
                )
            except Exception:
                checkbox = league_label.find_element(
                    By.XPATH,
                    "./ancestor::*[contains(@class,'SelectLeaguesModal')][1]//*[contains(@class,'SelectLeaguesModal_check')]"
                )

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", checkbox)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", checkbox)
            logger.info("Đã tick giải 'Giải Setka Cup'.")

        except Exception as e:
            logger.warning(f"Không thể chọn giải 'Giải Setka Cup': {e}")
        # =========================================================

        # ================== NHẤN NÚT ÁP DỤNG =====================
        try:
            logger.info("Đang nhấn nút 'Áp dụng'...")
            apply_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(((
                    By.CSS_SELECTOR,
                    "button.eventlist_asia_fe_SelectLeaguesModal_applyButton"
                )))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", apply_btn)
            time.sleep(0.5)
            apply_btn.click()
            logger.info("Đã nhấn nút 'Áp dụng'.")
        except Exception as e:
            logger.warning(f"Không thể nhấn nút 'Áp dụng': {e}")
        # =========================================================

        # ================== VÒNG LẶP KIỂM TRA MỖI 1 PHÚT ==================
        try:
            while True:
                logger.info("===== BẮT ĐẦU VÒNG QUÉT MỚI =====")

                # Scroll xuống trong khu vực danh sách trận
                logger.info("Đang scroll xuống trong khu vực danh sách trận...")
                scroll_event_list_container(driver, steps=6, step_size=350, pause=0.7)
                logger.info("Đã scroll xong.")

                # Tìm & gửi Telegram nếu có trận mới
                new_sent = check_and_notify_matches(driver)

                if new_sent == 0:
                    logger.info("Không có trận mới nào 1:2 hoặc 2:1 cần gửi Telegram.")
                else:
                    logger.info(f"Đã gửi Telegram cho {new_sent} trận mới.")

                logger.info("Đợi 60 giây trước lần quét tiếp theo...")
                time.sleep(60)

        except KeyboardInterrupt:
            logger.info("Nhận tín hiệu dừng (Ctrl+C). Kết thúc vòng lặp.")
        # ==================================================================

    except Exception as e:
        logger.exception(f"Lỗi xảy ra: {e}")

    finally:
        driver.quit()
        logger.info("Đã đóng trình duyệt.")


if __name__ == "__main__":
    main()
