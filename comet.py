import nextcord
from nextcord.ext import commands
from nextcord import SlashOption
from dotenv import load_dotenv
import asyncio
import json
import os
import datetime
import requests
import random
import re
import io
try:
    import websocket
    import _thread as thread
    import threading
except ImportError:
    websocket = None
    thread = None
    threading = None

load_dotenv()

discordBotToken = os.getenv("DISCORD_TOKEN")
PUSHBULLET_TOKEN = os.getenv("PUSHBULLET_TOKEN", "")
on_run = True

RESELLER_ROLE_ID = 1442087677502685326

RVIP_ROLE_ID = 1368744047774138410
SVIP_ROLE_ID = 1368744047774138409
VVIP_ROLE_ID = 1368744047774138408
VIP_ROLE_ID = 1368744047757365347
BUYER_ROLE_ID = 1428265439204741230

ENABLE_PRODUCT_BUTTON = True
EXCLUDED_PROMO_GUILD_ID = 11

ADMIN_CHANNEL_ID = 1482223005827334154
PURCHASE_LOG_CHANNEL_ID = 1483086458318491678
STOCK_LOG_CHANNEL_ID = 1445261988124164116
CHARGE_LOG_CHANNEL_ID = 1483092820599504896
BANK_REQUEST_CHANNEL_ID = 1443953577482653717
CHARGE_REQUEST_CHANNEL_ID = 1443953577482653717
STOCK_MANAGEMENT_CHANNEL_ID = 1443953608180629635
AUTO_VENDING_CHANNEL_IDS = [1428977980750692372]
REVIEW_CHANNEL_ID = 1482219056206581880

SERVICE_NAME = "김갑룡 자판기"
VENDING_MACHINE_IMAGE_URL = "https://media.discordapp.net/attachments/1482210707532677170/1482233172052934676/unnamed.webp?ex=69b78636&is=69b634b6&hm=b0e7e818b2d9ca5188c87f6d3a29b53e1cdc87d81c5b8186a9129080f7b79d00&=&format=webp&width=605&height=799"
VENDING_MACHINE_IMAGE_ENABLED = True 
VENDING_MACHINE_DESCRIPTION = """

아래이모지클릭으로 구매해주세요"""

MIN_CHARGE_AMOUNT = 500

MAX_BALANCE = 2**31 - 1
MAX_PRICE = 2**31 - 1
MAX_QUANTITY = 10000
MAX_STRING_LENGTH = 2000
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_PRODUCTS = 100
MAX_LOG_ENTRIES = 1000

VIP_LEVELS = {
    "rvip": {"min_amount": 300000, "discount": 0},
    "svip": {"min_amount": 150000, "discount": 0},
    "vvip": {"min_amount": 100000, "discount": 0},
    "vip": {"min_amount": 50000, "discount": 0},
    "구매자": {"min_amount": 1, "discount": 0}
}


RPC_MESSAGES = [
    " | 24시간 영업중"
]
RPC_UPDATE_INTERVAL = 1800
RPC_ERROR_RETRY_INTERVAL = 300




PENDING_CHARGES = {}
PROCESSED_CHARGE_MESSAGE_IDS = set()
PROCESSED_PUSHBULLET_NOTIFICATIONS = set()
REVIEWED_USERS = set()


def cleanup_old_pending_charges():
    current_time = datetime.datetime.now().timestamp()
    expired_users = []
    
    for user_id, charge_info in PENDING_CHARGES.items():
        if current_time - charge_info["timestamp"] > 86400:
            expired_users.append(user_id)
    
    for user_id in expired_users:
        del PENDING_CHARGES[user_id]


def safe_add(a, b):
    if a > MAX_BALANCE or b > MAX_BALANCE:
        raise ValueError("값이 너무 큽니다")
    result = a + b
    if result > MAX_BALANCE:
        raise ValueError("결과값이 최대값을 초과합니다")
    return result


def safe_multiply(a, b):
    if a > MAX_PRICE or b > MAX_QUANTITY:
        raise ValueError("값이 너무 큽니다")
    result = a * b
    if result > MAX_PRICE:
        raise ValueError("결과값이 최대값을 초과합니다")
    return result


def validate_string_length(text, max_length=MAX_STRING_LENGTH):
    if len(text) > max_length:
        raise ValueError(f"문자열이 너무 깁니다 (최대 {max_length}자)")
    return text


def truncate_text(text, max_length, suffix="..."):
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def split_long_text(text, max_length=1024):
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    lines = text.split('\n')
    for line in lines:
        if len(line) > max_length:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
            current_chunk = line
        elif len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line
        else:
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks if chunks else [text[:max_length]]


def safe_add_field(embed, name, value, inline=False, max_field_value_length=1024, max_field_name_length=256):
    try:
        safe_name = truncate_text(str(name), max_field_name_length)
        
        safe_value = str(value)
        if len(safe_value) > max_field_value_length:
            chunks = split_long_text(safe_value, max_field_value_length)
            for i, chunk in enumerate(chunks):
                field_name = safe_name if i == 0 else f"{safe_name} (계속 {i+1})"
                embed.add_field(name=field_name, value=chunk, inline=inline)
        else:
            embed.add_field(name=safe_name, value=safe_value, inline=inline)
    except Exception as e:
        try:
            error_msg = f"필드 추가 오류: {str(e)[:500]}"
            embed.add_field(name="오류", value=error_msg, inline=False)
        except:
            pass


def safe_set_description(embed, description, max_length=4096):
    try:
        safe_desc = truncate_text(str(description), max_length)
        embed.description = safe_desc
    except Exception as e:
        try:
            embed.description = f"설명 표시 오류: {str(e)[:500]}"
        except:
            pass


def safe_set_title(embed, title, max_length=256):
    try:
        safe_title = truncate_text(str(title), max_length)
        embed.title = safe_title
    except Exception as e:
        try:
            embed.title = "제목 표시 오류"
        except:
            pass


def validate_positive_int(value, max_value=None):
    try:
        int_value = int(value)
        if int_value < 0:
            raise ValueError("음수는 허용되지 않습니다")
        if max_value and int_value > max_value:
            raise ValueError(f"값이 너무 큽니다 (최대 {max_value})")
        return int_value
    except (ValueError, TypeError):
        raise ValueError("올바른 정수를 입력해주세요")


def load_json_data(filename):
    try:
        file_path = f'data/{filename}.json'
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            if file_size > MAX_FILE_SIZE:
                raise ValueError(f"파일이 너무 큽니다 (최대 {MAX_FILE_SIZE}바이트)")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        print(f"JSON 파싱 오류: {e}")
        return {}


def save_json_data(filename, data):
    os.makedirs('data', exist_ok=True)
    with open(f'data/{filename}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_bank_account():
    try:
        account_data = load_json_data('bank_account')
        if account_data and 'account' in account_data:
            return account_data['account']
        default_account = "888004408748케이뱅크"
        save_bank_account(default_account)
        return default_account
    except Exception as e:
        print(f"계좌 정보 로드 오류: {e}")
        return "888004408748케이뱅크"

def save_bank_account(account):
    try:
        account_data = {'account': account}
        save_json_data('bank_account', account_data)
    except Exception as e:
        print(f"계좌 정보 저장 오류: {e}")

def load_admin_ids():
    try:
        admin_data = load_json_data('admin_ids')
        if admin_data and 'admin_ids' in admin_data:
            return admin_data['admin_ids']
        default_admin_ids = [1202376647635128340, 1132688874238390312]
        save_admin_ids(default_admin_ids)
        return default_admin_ids
    except Exception as e:
        print(f"관리자 ID 로드 오류: {e}")
        return [1202376647635128340, 1132688874238390312]

def save_admin_ids(admin_ids_list):
    try:
        admin_data = {'admin_ids': admin_ids_list}
        save_json_data('admin_ids', admin_data)
    except Exception as e:
        print(f"관리자 ID 저장 오류: {e}")

BANK_ACCOUNT = load_bank_account()
admin_ids = load_admin_ids()


def get_category_emoji(category_name):
    emoji_data = load_json_data('category_emojis')
    if emoji_data and category_name in emoji_data:
        return emoji_data[category_name]
    return ""

def get_product_image_url(product_name, category_name=None):
    """제품의 이미지 URL을 가져옵니다."""
    image_data = load_json_data('product_images')
    if not image_data:
        return None
    
    if category_name and category_name in image_data:
        if product_name in image_data[category_name]:
            return image_data[category_name][product_name]
    
    if 'products' in image_data:
        if product_name in image_data['products']:
            return image_data['products'][product_name]
    
    return "https://media.discordapp.net/attachments/1442162293860339782/1443050626631078059/1758164593268.gif?ex=6927a91f&is=6926579f&hm=f4024cdf630cbd2bc156b3f5a1f469f4e820922200ccf7fe03131b6d1313f64f&="

def set_product_image_url(product_name, image_url, category_name=None):
    """제품의 이미지 URL을 저장합니다."""
    image_data = load_json_data('product_images')
    if not image_data:
        image_data = {}
    
    if category_name:
        if category_name not in image_data:
            image_data[category_name] = {}
        image_data[category_name][product_name] = image_url
    else:
        if 'products' not in image_data:
            image_data['products'] = {}
        image_data['products'][product_name] = image_url
    
    save_json_data('product_images', image_data)


def get_product_emoji(category_name, product_name):
    emoji_data = load_json_data('product_emojis')
    if emoji_data and category_name in emoji_data and product_name in emoji_data[category_name]:
        return emoji_data[category_name][product_name]
    return ""


def get_product_order(category_name):
    order_data = load_json_data('product_order')
    if order_data and category_name in order_data:
        return order_data[category_name]
    return []


def set_product_order(category_name, product_order):
    order_data = load_json_data('product_order')
    if not order_data:
        order_data = {}
    order_data[category_name] = product_order
    save_json_data('product_order', order_data)


def sort_products_by_order(products, category_name):
    products_list = list(products.items())
    products_list.sort(key=lambda x: x[1].get('price', 0))
    
    result = {}
    for product_name, product_data in products_list:
        result[product_name] = product_data
    
    return result

def get_user_data(guild_id, user_id):
    user_data = load_user_data()
    user_key = str(user_id)  
    
    if user_key not in user_data:
        user_data[user_key] = {
            'user_id': user_id,
            'balance': 0,
            'total_spent': 0,
            'vip_level': '유저',
            'created_at': datetime.datetime.now().isoformat(),
            'last_updated': datetime.datetime.now().isoformat()
        }
        save_user_data(user_data)
    
    return user_data[user_key]


def update_user_data(guild_id, user_id, updates):
    user_data = load_user_data()
    user_key = str(user_id) 
    
    if user_key not in user_data:
        user_data[user_key] = {
            'user_id': user_id,
                'balance': 0,
                'total_spent': 0,
            'vip_level': '유저',
            'created_at': datetime.datetime.now().isoformat(),
            'last_updated': datetime.datetime.now().isoformat()
        }
    for key, value in updates.items():
        if key in ['balance', 'total_spent']:
            user_data[user_key][key] = max(0, min(value, MAX_BALANCE))
        elif key == 'vip_level':
            user_data[user_key][key] = str(value)[:50]
        else:
            user_data[user_key][key] = value
    user_data[user_key]['last_updated'] = datetime.datetime.now().isoformat()
    total_spent = user_data[user_key]['total_spent']
    for level, info in VIP_LEVELS.items():
        if total_spent >= info['min_amount']:
            user_data[user_key]['vip_level'] = level
    
    save_user_data(user_data)
    return user_data[user_key]
def add_buy_record(guild_id, user_id, product_name, quantity, price, total_price, discount_amount, final_price):
    buy_history = load_buy_history()
    
    buy_record = {
        'id': len(buy_history) + 1,
        'guild_id': guild_id,
        'user_id': user_id,
        'product_name': product_name,
        'quantity': quantity,
        'price': price,
        'total_price': total_price,
        'discount_amount': discount_amount,
        'final_price': final_price,
        'timestamp': datetime.datetime.now().isoformat(),
        'date': datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M')
    }
    
    buy_history.append(buy_record)
    if len(buy_history) > MAX_LOG_ENTRIES:
        buy_history = buy_history[-MAX_LOG_ENTRIES:]
    
    save_buy_history(buy_history)
    return buy_record
def add_deposit_record(guild_id, user_id, amount, method, receipt_image=None, transaction_hash=None, depositor_name=None):
    deposit_history = load_deposit_history()
    
    deposit_record = {
        'id': len(deposit_history) + 1,
        'guild_id': guild_id,
        'user_id': user_id,
        'amount': amount,
        'method': method, 
        'receipt_image': receipt_image,
        'transaction_hash': transaction_hash,
        'depositor_name': depositor_name, 
        'timestamp': datetime.datetime.now().isoformat(),
        'date': datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M')
    }
    
    deposit_history.append(deposit_record)
    if len(deposit_history) > MAX_LOG_ENTRIES:
        deposit_history = deposit_history[-MAX_LOG_ENTRIES:]
    
    save_deposit_history(deposit_history)
    return deposit_record
def get_products(guild_id):
    data = load_json_data(f'guild_{guild_id}')
    if 'products' not in data:
        data['products'] = {}
        save_json_data(f'guild_{guild_id}', data)
    return data['products']
def update_products(guild_id, products):
    data = load_json_data(f'guild_{guild_id}')
    data['products'] = products
    save_json_data(f'guild_{guild_id}', data)
def get_product_stock(guild_id, product_name):
    stock_base_dir = 'stock'
    if not os.path.exists(stock_base_dir):
        return []
    stock_items = []
    categories = get_categories_from_stock_folder() 
    if categories:
        for category in categories:
            category_path = os.path.join(stock_base_dir, category)
            if os.path.exists(category_path) and os.path.isdir(category_path):
                for filename in os.listdir(category_path):
                    if filename.endswith('.txt'):
                        parsed = parse_filename(filename)
                        if not parsed or 'product_name' not in parsed:
                            continue
                        file_product_name = parsed['product_name']
                        if file_product_name == product_name:
                                file_path = os.path.join(category_path, filename)
                                try:
                                    file_size = os.path.getsize(file_path)
                                    if file_size > MAX_FILE_SIZE:
                                        print(f"파일이 너무 큽니다: {filename}")
                                        continue
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        lines = f.readlines()
                                        if len(lines) > MAX_LOG_ENTRIES:
                                            lines = lines[:MAX_LOG_ENTRIES]
                                        for line in lines:
                                            line = line.strip()
                                            if line and len(line) <= MAX_STRING_LENGTH:
                                                stock_items.append(line)
                                except Exception as e:
                                    print(f"파일 읽기 오류: {filename} - {e}")
    else:
        for filename in os.listdir(stock_base_dir):
            if filename.endswith('.txt'):
                parsed = parse_filename(filename)
                if not parsed or 'product_name' not in parsed:
                    continue
                file_product_name = parsed['product_name']
                if file_product_name == product_name:
                        file_path = os.path.join(stock_base_dir, filename)
                        try:
                            file_size = os.path.getsize(file_path)
                            if file_size > MAX_FILE_SIZE:
                                print(f"파일이 너무 큽니다: {filename}")
                                continue
                            with open(file_path, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                                if len(lines) > MAX_LOG_ENTRIES:
                                    lines = lines[:MAX_LOG_ENTRIES]
                            for line in lines:
                                line = line.strip()
                                if line and len(line) <= MAX_STRING_LENGTH:
                                    stock_items.append(line)
                        except Exception as e:
                            print(f"파일 읽기 오류: {filename} - {e}")
    return stock_items
async def add_product_stock_async(guild_id, product_name, content):
    validate_string_length(product_name, 100) 
    validate_string_length(content, MAX_STRING_LENGTH)
    stock_base_dir = 'stock'
    os.makedirs(stock_base_dir, exist_ok=True)
    timestamp = int(datetime.datetime.now().timestamp() * 1000)
    filename = f"{product_name}_0_{timestamp}.txt" 
    file_path = os.path.join(stock_base_dir, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    try:
        stock_log_channel = bot.get_channel(STOCK_LOG_CHANNEL_ID)
        if stock_log_channel:
            product_info = get_product_info_from_stock(product_name)
            price = product_info['price'] if product_info else 0
            category = product_info['category'] if product_info else None
            
            if price > 0:
                price_str = f"{price:,}원"
                title = f"{product_name} [{price_str}]"
            else:
                title = product_name
            
            stock_count = len([line.strip() for line in content.split('\n') if line.strip()]) if content else 1
            
            image_url = get_product_image_url(product_name, category)
            
            embed = nextcord.Embed(
                title=title,
                description=f"상품이 **{stock_count}개** 입고되었습니다.",
                color=0x8B5CF6  # 보라색 계열
            )
            
            if image_url:
                embed.set_image(url=image_url)
            
            embed.timestamp = datetime.datetime.now()
            await stock_log_channel.send(embed=embed)
    except Exception as e:
        print(f"입고로그 전송 실패: {e}")
def add_product_stock(guild_id, product_name, content):
    validate_string_length(product_name, 100) 
    validate_string_length(content, MAX_STRING_LENGTH) 
    stock_base_dir = 'stock'
    os.makedirs(stock_base_dir, exist_ok=True)
    timestamp = int(datetime.datetime.now().timestamp() * 1000)
    filename = f"{product_name}_0_{timestamp}.txt"
    file_path = os.path.join(stock_base_dir, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"재고 추가됨: {product_name} - {filename}")
def remove_product_stock(guild_id, product_name, quantity):
    quantity = validate_positive_int(quantity, MAX_QUANTITY)
    validate_string_length(product_name, 100)
    stock_base_dir = 'stock'
    if not os.path.exists(stock_base_dir):
        print(f"STOCK 폴더가 존재하지 않습니다.")
        return []
    removed_items = []
    remaining_quantity = quantity
    categories = get_categories_from_stock_folder()
    if categories:
        for category in categories:
            if remaining_quantity <= 0:
                break
            category_path = os.path.join(stock_base_dir, category)
            if os.path.exists(category_path) and os.path.isdir(category_path):
                for filename in os.listdir(category_path):
                    if filename.endswith('.txt') and remaining_quantity > 0:
                        parsed = parse_filename(filename)
                        if not parsed or 'product_name' not in parsed:
                            continue
                        file_product_name = parsed['product_name']
                        if file_product_name == product_name:
                                file_path = os.path.join(category_path, filename)
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        lines = f.readlines()
                                    lines_to_keep = []
                                    for i, line in enumerate(lines):
                                        line = line.strip()
                                        if line and remaining_quantity > 0:
                                            removed_items.append(line)
                                            remaining_quantity -= 1
                                        else:
                                            lines_to_keep.append(lines[i])
                                    with open(file_path, 'w', encoding='utf-8') as f:
                                        if lines_to_keep:
                                            f.writelines(lines_to_keep)
                                        
                                except:
                                    pass
    else:
        for filename in os.listdir(stock_base_dir):
            if filename.endswith('.txt') and remaining_quantity > 0:
                parsed = parse_filename(filename)
                file_product_name = parsed['product_name']
                if file_product_name == product_name:
                        file_path = os.path.join(stock_base_dir, filename)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                            lines_to_keep = []
                            for i, line in enumerate(lines):
                                line = line.strip()
                                if line and remaining_quantity > 0:
                                    removed_items.append(line)
                                    remaining_quantity -= 1
                                else:
                                    lines_to_keep.append(lines[i])
                            with open(file_path, 'w', encoding='utf-8') as f:
                                if lines_to_keep:
                                    f.writelines(lines_to_keep)
                            
                        except:
                            pass
    
    return removed_items
def get_product_stock_count(guild_id, product_name):
    stock_base_dir = 'stock'
    if not os.path.exists(stock_base_dir):
        return 0
    count = 0
    categories = get_categories_from_stock_folder()
    
    if categories:
        for category in categories:
            category_path = os.path.join(stock_base_dir, category)
            if os.path.exists(category_path) and os.path.isdir(category_path):
                try:
                    for filename in os.listdir(category_path):
                        if filename.endswith('.txt'):
                            parsed = parse_filename(filename)
                            file_product_name = parsed['product_name']
                            if file_product_name == product_name:
                                file_path = os.path.join(category_path, filename)
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        lines = f.readlines()
                                        valid_lines = [line.strip() for line in lines if line.strip() and len(line.strip()) > 0]
                                        count += len(valid_lines)
                                except Exception as e:
                                    print(f"재고 파일 읽기 오류: {filename} - {e}")
                                    continue
                except Exception as e:
                    print(f"카테고리 읽기 오류: {category} - {e}")
                    continue
    else:
        try:
            for filename in os.listdir(stock_base_dir):
                if filename.endswith('.txt'):
                    parsed = parse_filename(filename)
                    file_product_name = parsed['product_name']
                    if file_product_name == product_name:
                        file_path = os.path.join(stock_base_dir, filename)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                                valid_lines = [line.strip() for line in lines if line.strip() and len(line.strip()) > 0]
                                count += len(valid_lines)
                        except Exception as e:
                            print(f"재고 파일 읽기 오류: {filename} - {e}")
                            continue
        except Exception as e:
            print(f"재고 디렉토리 읽기 오류: {e}")
    
    return count
def parse_filename(filename):
    try:
        name_without_ext = filename.replace('.txt', '').replace('.TXT', '')
        if '_' not in name_without_ext:
            return {'product_name': name_without_ext, 'price': 0, 'timestamp': None}
        
        parts = name_without_ext.split('_')
        if len(parts) < 2:
            return {'product_name': name_without_ext, 'price': 0, 'timestamp': None}
        
        last_part = parts[-1].strip()
        timestamp = None
        if last_part.isdigit() and len(last_part) >= 10:
            try:
                timestamp = int(last_part)
                if timestamp < 0 or timestamp > 2**63 - 1:
                    timestamp = None
            except (ValueError, OverflowError):
                timestamp = None
        
        if timestamp is not None and len(parts) >= 2:
            price_part = parts[-2].strip()
            if price_part.isdigit():
                try:
                    price = int(price_part)
                    price = max(0, min(price, MAX_PRICE))
                except (ValueError, OverflowError):
                    price = 0
            else:
                price = 0
            product_name = '_'.join(parts[:-2]) if len(parts) > 2 else parts[0]
        else:
            last_part_clean = parts[-1].strip()
            if last_part_clean.isdigit():
                try:
                    price = int(last_part_clean)
                    price = max(0, min(price, MAX_PRICE))
                except (ValueError, OverflowError):
                    price = 0
                product_name = '_'.join(parts[:-1]) if len(parts) > 1 else parts[0]
            else:
                price = 0
                product_name = name_without_ext
        
        return {
            'product_name': product_name,
            'price': price,
            'timestamp': timestamp
        }
    except Exception as e:
        print(f"파일명 파싱 오류: {filename} - {e}")
        return {'product_name': filename.replace('.txt', '').replace('.TXT', ''), 'price': 0, 'timestamp': None}
def get_price_from_filename(filename):
    parsed = parse_filename(filename)
    if not parsed or 'price' not in parsed:
        return 0
    return parsed['price']
def get_product_info_from_stock(product_name, category_name=None):
    stock_base_dir = 'stock'
    if not os.path.exists(stock_base_dir):
        return None
    
    categories = [category_name] if category_name else get_categories_from_stock_folder()
    
    for category in categories:
        if category_name and category != category_name:
            continue
        category_path = os.path.join(stock_base_dir, category)
        if os.path.exists(category_path) and os.path.isdir(category_path):
            for filename in os.listdir(category_path):
                if filename.endswith('.txt'):
                    parsed = parse_filename(filename)
                    file_product_name = parsed['product_name']
                    if file_product_name == product_name:
                        price = parsed['price']
                        return {
                            'name': product_name,
                            'category': category,
                            'price': price,
                            'filename': filename
                        }
    
    if not category_name:
        for filename in os.listdir(stock_base_dir):
            if filename.endswith('.txt'):
                parsed = parse_filename(filename)
                if not parsed or 'product_name' not in parsed or 'price' not in parsed:
                    continue
                file_product_name = parsed['product_name']
                if file_product_name == product_name:
                    price = parsed['price']
                    return {
                        'name': product_name,
                        'category': None,
                        'price': price,
                        'filename': filename
                    }
    
    return None
def get_categories_from_stock_folder():
    stock_base_dir = 'stock'
    if not os.path.exists(stock_base_dir):
        return []
    categories = []
    try:
        for item in os.listdir(stock_base_dir):
            item_path = os.path.join(stock_base_dir, item)
            if os.path.isdir(item_path):
                categories.append(item)
    except Exception as e:
        print(f"카테고리 읽기 오류: {e}")
    
    category_order = ["한국서버", "아시아서버", "랜덤서버"]
    ordered_categories = []
    unordered_categories = []
    
    for order_keyword in category_order:
        for cat in categories:
            if order_keyword in cat and cat not in ordered_categories:
                ordered_categories.append(cat)
                break
    
    for cat in categories:
        if cat not in ordered_categories:
            unordered_categories.append(cat)
    
    return ordered_categories + sorted(unordered_categories)
def get_products_from_category(category_name):
    stock_base_dir = 'stock'
    category_path = os.path.join(stock_base_dir, category_name)
    
    if not os.path.exists(category_path) or not os.path.isdir(category_path):
        return {}
    products = {}
    try:
        file_count = 0
        for filename in os.listdir(category_path):
            if file_count >= MAX_PRODUCTS:
                print(f"최대 제품 수({MAX_PRODUCTS})에 도달했습니다.")
                break
            if filename.endswith('.txt'):
                file_path = os.path.join(category_path, filename)
                try:
                    file_size = os.path.getsize(file_path)
                    if file_size > MAX_FILE_SIZE:
                        print(f"파일이 너무 큽니다: {filename}")
                        continue
                except:
                    continue
                parsed = parse_filename(filename)
                if not parsed or 'product_name' not in parsed or 'price' not in parsed:
                    continue
                product_name = parsed['product_name']
                price = parsed['price']
                if price <= 0:
                    continue
                if len(product_name) > 100:
                    print(f"제품명이 너무 깁니다: {product_name}")
                    continue
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        if len(lines) > MAX_LOG_ENTRIES:
                            lines = lines[:MAX_LOG_ENTRIES]
                        stock_count = len([line.strip() for line in lines if line.strip()])
                except:
                    stock_count = 0
                if product_name in products:
                    products[product_name]['stock'] = safe_add(products[product_name]['stock'], stock_count)
                else:
                    products[product_name] = {
                        'name': product_name,
                        'price': price,
                        'stock': stock_count,
                        'category': category_name,
                        'description': f"{product_name} 제품입니다."
                    }
                
                file_count += 1
    except Exception as e:
        print(f"카테고리 {category_name} 읽기 오류: {e}")
    
    products = sort_products_by_order(products, category_name)
    return products
def get_products_from_stock_folder(guild_id):
    stock_base_dir = 'stock'
    if not os.path.exists(stock_base_dir):
        return {}
    all_products = {}
    categories = get_categories_from_stock_folder()
    if categories:
        for category in categories:
            category_products = get_products_from_category(category)
            all_products.update(category_products)
    else:
        try:
            file_count = 0
            for filename in os.listdir(stock_base_dir):
                if file_count >= MAX_PRODUCTS:
                    print(f"최대 제품 수({MAX_PRODUCTS})에 도달했습니다.")
                    break
                if filename.endswith('.txt'):
                    file_path = os.path.join(stock_base_dir, filename)
                    try:
                        file_size = os.path.getsize(file_path)
                        if file_size > MAX_FILE_SIZE:
                            print(f"파일이 너무 큽니다: {filename}")
                            continue
                    except:
                        continue
                    parsed = parse_filename(filename)
                    product_name = parsed['product_name']
                    price = parsed['price']
                    if price <= 0:
                        print(f"올바르지 않은 가격의 제품을 건너뜁니다: {filename}")
                        continue
                    if len(product_name) > 100:
                        print(f"제품명이 너무 깁니다: {product_name}")
                        continue
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            if len(lines) > MAX_LOG_ENTRIES:
                                lines = lines[:MAX_LOG_ENTRIES]
                            stock_count = len([line.strip() for line in lines if line.strip()])
                    except:
                        stock_count = 0
                    if product_name in all_products:
                        all_products[product_name]['stock'] = safe_add(all_products[product_name]['stock'], stock_count)
                    else:
                        all_products[product_name] = {
                            'name': product_name,
                            'price': price,
                            'stock': stock_count,
                            'category': '기타',
                            'description': f"{product_name} 제품입니다."
                        }
                    
                    file_count += 1
        except Exception as e:
            print(f"STOCK 폴더 읽기 오류: {e}")
    return all_products
def add_purchase_log(guild_id, user_id, product_name, quantity, total_price, discount_amount=0):
    final_price = total_price - discount_amount
    return add_buy_record(guild_id, user_id, product_name, quantity, total_price, total_price, discount_amount, final_price)
def add_stock_log(guild_id, product_name, quantity, action="입고"):
    data = load_json_data(f'guild_{guild_id}')
    if 'stock_logs' not in data:
        data['stock_logs'] = []
    if len(data['stock_logs']) >= MAX_LOG_ENTRIES:
        data['stock_logs'] = data['stock_logs'][-MAX_LOG_ENTRIES//2:]
    log_entry = {
        'timestamp': datetime.datetime.now().isoformat(),
        'product_name': validate_string_length(product_name, 100),
        'quantity': validate_positive_int(quantity, MAX_QUANTITY),
        'action': validate_string_length(action, 50)
    }
    data['stock_logs'].append(log_entry)
    save_json_data(f'guild_{guild_id}', data)
def add_charge_log(guild_id, user_id, amount, status="대기중", receipt_image=None, method="계좌이체", depositor_name=None):
    return add_deposit_record(guild_id, user_id, amount, method, receipt_image, depositor_name)
def update_charge_log_status(guild_id, log_index, status):
    data = load_json_data(f'guild_{guild_id}')
    if 'charge_logs' in data and log_index < len(data['charge_logs']):
        data['charge_logs'][log_index]['status'] = status
        save_json_data(f'guild_{guild_id}', data)
def get_vip_level(total_spent):
    """이용금액에 따라 VIP 등급을 반환"""
    for level in ["rvip", "svip", "vvip", "vip", "구매자"]:
        if level in VIP_LEVELS and total_spent >= VIP_LEVELS[level]['min_amount']:
            return level
    return '구매자'
def is_reseller(user, guild=None):
    """사용자가 리셀러 역할을 가지고 있는지 확인"""
    if hasattr(user, 'roles') and user.roles:
        return any(role.id == RESELLER_ROLE_ID for role in user.roles)
    if guild and hasattr(user, 'id'):
        member = guild.get_member(user.id)
        if member and hasattr(member, 'roles') and member.roles:
            return any(role.id == RESELLER_ROLE_ID for role in member.roles)
    return False

def calculate_reseller_bonus(amount, user, guild=None):
    """리셀러인 경우 20% 추가 충전 금액 계산"""
    if is_reseller(user, guild):
        bonus = int(amount * 0.2)
        return amount + bonus
    return amount

def apply_reseller_bonus_to_charge(amount, user_id, guild):
    """충전 금액에 리셀러 보너스를 적용하는 헬퍼 함수"""
    member = guild.get_member(user_id) if guild else None
    if member:
        return calculate_reseller_bonus(amount, member, guild)
    else:
        user_obj = bot.get_user(user_id)
        if user_obj:
            return calculate_reseller_bonus(amount, user_obj, guild)
    return amount

def calculate_discount(total_price, vip_level):
    return 0
def get_role_id_by_vip_level(vip_level):
    return BUYER_ROLE_ID
async def pending_charge_timeout_monitor():
    while True:
        try:
            now = datetime.datetime.now().timestamp()
            to_process = []
            for user_id, info in list(PENDING_CHARGES.items()):
                ts = info.get("timestamp", 0)
                if ts and now - ts > 300:
                    to_process.append((user_id, info))
            for uid, info in to_process:
                try:
                    amount = info.get("amount", 0)
                    depositor_name = info.get("depositor_name", "알 수 없음")
                    
                    if not info.get("timeout_sent", False):
                        try:
                            user = bot.get_user(uid)
                            if user:
                                em = nextcord.Embed(title="⚠️ 충전 확인 요청", color=0xffa500)
                                em.add_field(name="안내", value="입금이 제대로 확인이 안되었습니다.\n입금내역을 찍어서 보내주세요.\n빠른 시일 내로 확인 후 승인해드리겠습니다.", inline=False)
                                await user.send(embed=em)
                                info["timeout_sent"] = True
                                PENDING_CHARGES[uid] = info
                        except Exception:
                            pass
                    
                    try:
                        charge_channel = bot.get_channel(CHARGE_LOG_CHANNEL_ID)
                        if charge_channel:
                            guild_id = list(bot.guilds)[0].id if bot.guilds else None
                            if guild_id:
                                log_index = add_charge_log(guild_id, uid, amount, status="대기중", method="계좌이체", depositor_name=depositor_name)
                                
                                view = TimeoutChargeApprovalView(uid, amount, log_index, depositor_name)
                                
                                timeout_embed = nextcord.Embed(title="⏰ 충전 확인 요청 (5분 타임아웃)", color=0xffa500)
                                timeout_embed.add_field(name="사용자", value=f"<@{uid}>", inline=True)
                                timeout_embed.add_field(name="입금자명", value=depositor_name, inline=True)
                                timeout_embed.add_field(name="금액", value=f"{amount:,}원", inline=True)
                                timeout_embed.add_field(name="안내", value="5분 동안 자동 승인되지 않아 수동 확인이 필요합니다.\n입금내역 확인 후 승인 또는 거절해주세요.", inline=False)
                                timeout_embed.timestamp = datetime.datetime.now()
                                
                                await charge_channel.send(embed=timeout_embed, view=view)
                    except Exception as e:
                        print(f"타임아웃 충전 로그 전송 오류: {e}")
                except Exception as e:
                    print(f"타임아웃 처리 오류: {e}")
        except Exception:
            pass
        await asyncio.sleep(60)

pushbullet_ws = None
pushbullet_ws_thread = None

def parse_bank_notification(package_name, body):
    """은행 앱 알림을 파싱하여 입금자명과 금액을 추출합니다."""
    body_normalized = body.replace("\n", " ")
    message_parts = body_normalized.replace("원", "").replace(",", "").split(' ')
    displayname = ""
    count = 0
    
    try:
        if package_name == "com.IBK.SmartPush.app":
            sp = body_normalized.split(" ")
            if len(sp) >= 3:
                displayname = sp[2]
                count = int(sp[1].replace("원", "").replace(",", ""))
            print(f"BankAPI[SUCCESS]: com.IBK.SmartPush.app - {displayname}, {count}원")
        elif package_name == "com.nh.mobilenoti":
            if len(message_parts) >= 6:
                displayname = message_parts[5]
                count_str = message_parts[1].replace("입금", "").replace("원", "").replace(",", "")
                count = int(count_str)
            print(f"BankAPI[SUCCESS]: com.nh.mobilenoti - {displayname}, {count}원")
        elif package_name == "com.wooribank.smart.npib":
            sp = body_normalized.split(" ")
            if len(sp) >= 6:
                displayname = sp[1]
                count = int(sp[5].replace("원", "").replace(",", ""))
            print(f"BankAPI[SUCCESS]: com.wooribank.smart.npib - {displayname}, {count}원")
        elif package_name == "com.kakaobank.channel":
            name = body_normalized.split(" ")
            if len(name) >= 6:
                displayname = name[5]
                count = int(name[4].replace(",", "").replace("원", ""))
            print(f"BankAPI[SUCCESS]: com.kakaobank.channel - {displayname}, {count}원")
        else:
            import re
            amt_match = re.search(r"입금\s*([\d,]+)원", body)
            if not amt_match:
                amt_match = re.search(r"([\d,]+)원\s*입금", body)
            if amt_match:
                count = int(amt_match.group(1).replace(",", ""))
                lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
                for ln in lines:
                    if re.search(r"[가-힣]{2,4}", ln) and "원" not in ln and "잔액" not in ln:
                        displayname = re.sub(r"[^가-힣]", "", ln)
                        if 2 <= len(displayname) <= 4:
                            break
            print(f"BankAPI[GENERIC]: {package_name} - {displayname}, {count}원")
        
        if count > 0 and displayname:
            return displayname, count
        return None, None
    except Exception as e:
        print(f"BankAPI[ERROR]: 파싱 오류 - {e}")
        return None, None

async def process_pushbullet_notification(package_name, body):
    """PushBullet 알림을 처리하여 자동충전을 수행합니다."""
    import re
    
    if not body or not package_name:
        return False
    
    bank_packages = [
        "com.IBK.SmartPush.app",
        "com.nh.mobilenoti",
        "com.wooribank.smart.npib",
        "com.kakaobank.channel"
    ]
    
    if package_name not in bank_packages:
        if "입금" not in body:
            return False
    
    depositor, amount = parse_bank_notification(package_name, body)
    
    if not depositor or not amount or amount <= 0:
        return False
    
    def normalize_name(n: str) -> str:
        normalized = re.sub(r"[^가-힣]", "", n)
        bank_words = ["입출금통장", "통장", "계좌", "입금", "출금"]
        for word in bank_words:
            normalized = normalized.replace(word, "")
        return normalized
    
    def names_match(name1: str, name2: str) -> bool:
        """이름 매칭 함수 - 부분 일치도 허용"""
        norm1 = normalize_name(name1)
        norm2 = normalize_name(name2)
        if norm1 == norm2 or name1.strip() == name2.strip():
            return True
        if norm1 in norm2 or norm2 in norm1:
            min_len = min(len(norm1), len(norm2))
            if min_len >= 2:
                return True
        if len(norm1) >= 2 and len(norm2) >= 2:
            if norm1[0] == norm2[0]:
                if len(norm1) == len(norm2) or abs(len(norm1) - len(norm2)) <= 1:
                    if norm1[-1] == norm2[-1]:
                        return True
                    if len(norm1) >= 2 and len(norm2) >= 2:
                        if norm1[:2] == norm2[:2]:
                            return True
        return False
    
    parsed_norm = normalize_name(depositor)
    cleanup_old_pending_charges()
    match_user_id = None
    for uid, info in PENDING_CHARGES.items():
        pending_name = str(info.get("depositor_name", ""))
        if info.get("amount") == amount:
            if names_match(pending_name, depositor):
                match_user_id = uid
                break
    
    if not match_user_id:
        print(f"PushBullet 자동승인 매칭 실패 - 금액: {amount}원, 추출된 입금자명: '{depositor}', 대기중인 요청: {[(uid, info.get('depositor_name'), info.get('amount')) for uid, info in PENDING_CHARGES.items()]}")
        return False
    
    guild_id = list(bot.guilds)[0].id if bot.guilds else None
    if not guild_id:
        return False
    
    credited_amount = amount
    try:
        guild = bot.get_guild(guild_id)
        if guild:
            credited_amount = apply_reseller_bonus_to_charge(credited_amount, match_user_id, guild)
    except Exception:
        pass
    
    user_data = get_user_data(guild_id, match_user_id)
    user_data['balance'] = safe_add(user_data['balance'], credited_amount)
    save_user_data(load_user_data())
    update_user_data(guild_id, match_user_id, user_data)
    
    def normalize_depositor_name(name: str) -> str:
        normalized = re.sub(r"[^가-힣]", "", name)
        bank_words = ["입출금통장", "통장", "계좌", "입금", "출금"]
        for word in bank_words:
            normalized = normalized.replace(word, "")
        return normalized.strip() if normalized.strip() else name
    
    clean_depositor = normalize_depositor_name(depositor)
    add_deposit_record(guild_id, match_user_id, credited_amount, method="계좌이체 (PushBullet)", depositor_name=clean_depositor)
    
    try:
        member = bot.get_user(match_user_id)
        if member:
            dm = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
            dm.add_field(name="입금자명", value=clean_depositor, inline=True)
            if credited_amount > amount:
                dm.add_field(name="입금 금액", value=f"{amount:,}원", inline=True)
                dm.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - amount:,}원", inline=True)
            dm.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
            dm.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
            await member.send(embed=dm)
    except Exception:
        pass
    
    try:
        charge_channel = bot.get_channel(CHARGE_LOG_CHANNEL_ID)
        if charge_channel:
            ok = nextcord.Embed(title="승인되었습니다", color=0x2ecc71)
            ok.add_field(name="입금자명", value=clean_depositor, inline=True)
            if credited_amount > amount:
                ok.add_field(name="입금 금액", value=f"{amount:,}원", inline=True)
                ok.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - amount:,}원", inline=True)
            ok.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
            ok.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
            ok.add_field(name="사용자", value=f"<@{match_user_id}>", inline=False)
            await charge_channel.send(embed=ok)
    except Exception:
        pass
    
    try:
        charge_request_channel = bot.get_channel(CHARGE_REQUEST_CHANNEL_ID)
        if charge_request_channel:
            request_ok = nextcord.Embed(title="승인되었습니다", color=0x2ecc71)
            request_ok.add_field(name="입금자명", value=clean_depositor, inline=True)
            if credited_amount > amount:
                request_ok.add_field(name="입금 금액", value=f"{amount:,}원", inline=True)
                request_ok.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - amount:,}원", inline=True)
            request_ok.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
            request_ok.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
            request_ok.add_field(name="사용자", value=f"<@{match_user_id}>", inline=False)
            await charge_request_channel.send(embed=request_ok)
    except Exception:
        pass
    
    try:
        charge_info = PENDING_CHARGES.get(match_user_id, {})
        request_message_id = charge_info.get("message_id")
        if request_message_id:
            req_channel = bot.get_channel(BANK_REQUEST_CHANNEL_ID)
            if req_channel:
                try:
                    request_msg = await req_channel.fetch_message(request_message_id)
                    if request_msg and request_msg.components:
                        disabled_view = nextcord.ui.View(timeout=None)
                        for component in request_msg.components:
                            for item in component.children:
                                if isinstance(item, nextcord.ui.Button):
                                    disabled_btn = nextcord.ui.Button(
                                        label=item.label or "승인",
                                        style=item.style,
                                        emoji=item.emoji if item.emoji else None,
                                        disabled=True,
                                        custom_id=item.custom_id
                                    )
                                    disabled_view.add_item(disabled_btn)
                        await request_msg.edit(view=disabled_view)
                except (nextcord.errors.NotFound, nextcord.errors.HTTPException) as e:
                    print(f"충전 요청 메시지 버튼 비활성화 실패: {e}")
    except Exception as e:
        print(f"PushBullet 자동 승인 버튼 비활성화 오류: {e}")
    
    
    try:
        del PENDING_CHARGES[match_user_id]
    except Exception:
        pass
    
    return True

def pushbullet_ws_on_message(ws, message):
    """WebSocket 메시지 수신 핸들러"""
    try:
        obj = json.loads(message)
        
        if obj.get("type") == "push":
            push = obj.get("push", {})
            package_name = push.get("package_name", "")
            body = push.get("body", "")
            title = push.get("title", "")
            
            try:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_entry = f"[{timestamp}] Type: push\n"
                if package_name:
                    log_entry += f"Package: {package_name}\n"
                if title:
                    log_entry += f"Title: {title}\n"
                if body:
                    log_entry += f"Body: {body}\n"
                log_entry += f"{'='*50}\n\n"
                with open("푸쉬불렛.txt", "a", encoding="utf-8") as f:
                    f.write(log_entry)
            except Exception as e:
                print(f"푸쉬불렛 로그 저장 오류: {e}")
            
            if not body or not package_name:
                return
            
            print(f"PushBullet 알림 수신: {package_name}\n본문: {body}")
            
            if bot and bot.loop:
                future = asyncio.run_coroutine_threadsafe(
                    process_pushbullet_notification(package_name, body),
                    bot.loop
                )
                try:
                    future.result(timeout=10)
                except Exception as e:
                    print(f"PushBullet 알림 처리 오류: {e}")
    except Exception as e:
        print(f"PushBullet WebSocket 메시지 처리 오류: {e}")

def pushbullet_ws_on_error(ws, error):
    """WebSocket 오류 핸들러"""
    print(f"PushBullet WebSocket 오류: {error}")

def pushbullet_ws_on_close(ws, close_status_code, close_msg):
    """WebSocket 종료 핸들러 - 자동 재연결"""
    print(f"PushBullet WebSocket 연결 종료 (코드: {close_status_code})")
    if PUSHBULLET_TOKEN:
        import time
        time.sleep(3)
        print("PushBullet WebSocket 자동 재연결 시도 중...")
        try:
            asyncio.run_coroutine_threadsafe(
                start_pushbullet_websocket(),
                bot.loop
            )
        except Exception as e:
            print(f"PushBullet 자동 재연결 오류: {e}")
            time.sleep(10)
            try:
                asyncio.run_coroutine_threadsafe(
                    start_pushbullet_websocket(),
                    bot.loop
                )
            except Exception as e2:
                print(f"PushBullet 재연결 재시도 오류: {e2}")

def pushbullet_ws_on_open(ws):
    """WebSocket 연결 핸들러"""
    print("PushBullet WebSocket 연결 성공")

def run_pushbullet_websocket():
    """WebSocket을 별도 스레드에서 실행 (자동 재연결 포함)"""
    global pushbullet_ws
    if not PUSHBULLET_TOKEN or not websocket:
        return
    
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            ws_url = f"wss://stream.pushbullet.com/websocket/{PUSHBULLET_TOKEN}"
            pushbullet_ws = websocket.WebSocketApp(
                ws_url,
                on_message=pushbullet_ws_on_message,
                on_error=pushbullet_ws_on_error,
                on_close=pushbullet_ws_on_close
            )
            pushbullet_ws.on_open = pushbullet_ws_on_open
            pushbullet_ws.run_forever()
            break
        except Exception as e:
            retry_count += 1
            print(f"PushBullet WebSocket 실행 오류 (재시도 {retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                import time
                wait_time = min(5 * retry_count, 30)  # 최대 30초까지 대기
                print(f"{wait_time}초 후 재연결 시도...")
                time.sleep(wait_time)
            else:
                print("PushBullet WebSocket 최대 재시도 횟수 초과")

async def start_pushbullet_websocket():
    """PushBullet WebSocket 연결 시작"""
    global pushbullet_ws_thread
    
    if not PUSHBULLET_TOKEN:
        print("PushBullet 토큰이 설정되지 않았습니다.")
        return
    
    if not websocket:
        print("websocket-client 라이브러리가 설치되지 않았습니다. 'pip install websocket-client'를 실행하세요.")
        return
    
    if pushbullet_ws_thread and isinstance(pushbullet_ws_thread, threading.Thread) and pushbullet_ws_thread.is_alive():
        print("PushBullet WebSocket이 이미 실행 중입니다.")
        return
    
    await bot.wait_until_ready()
    
    if threading:
        pushbullet_ws_thread = threading.Thread(target=run_pushbullet_websocket, daemon=True)
        pushbullet_ws_thread.start()
        print("PushBullet WebSocket 연결 시작")
    elif thread:
        pushbullet_ws_thread = thread.start_new_thread(run_pushbullet_websocket, ())
        print("PushBullet WebSocket 연결 시작 (fallback mode)")
    else:
        print("스레드 모듈을 사용할 수 없습니다.")

async def pushbullet_notification_monitor():
    """PushBullet WebSocket 연결 관리 및 자동 재연결 모니터링"""
    await bot.wait_until_ready()
    await asyncio.sleep(5)  # 봇이 완전히 준비될 때까지 대기
    
    if PUSHBULLET_TOKEN:
        await start_pushbullet_websocket()
    else:
        print("PushBullet 토큰이 설정되지 않아 WebSocket을 시작하지 않습니다.")
    
    while True:
        try:
            await asyncio.sleep(30)
            
            if not PUSHBULLET_TOKEN:
                continue
            
            import sys
            current_module = sys.modules[__name__]
            ws_obj = getattr(current_module, 'pushbullet_ws', None)
            ws_thread = getattr(current_module, 'pushbullet_ws_thread', None)
            
            if ws_thread and isinstance(ws_thread, threading.Thread) and ws_thread.is_alive():
                if ws_obj:
                    try:
                        if hasattr(ws_obj, 'sock') and ws_obj.sock:
                            if not (hasattr(ws_obj.sock, 'connected') and ws_obj.sock.connected):
                                print("PushBullet WebSocket 연결 끊김 감지 - 재연결 시도...")
                                await start_pushbullet_websocket()
                        else:
                            print("PushBullet WebSocket 소켓 없음 - 재연결 시도...")
                            await start_pushbullet_websocket()
                    except:
                        print("PushBullet WebSocket 상태 확인 실패 - 재연결 시도...")
                        await start_pushbullet_websocket()
                else:
                    print("PushBullet WebSocket 객체 없음 - 재연결 시도...")
                    await start_pushbullet_websocket()
            elif PUSHBULLET_TOKEN and (not ws_thread or not (isinstance(ws_thread, threading.Thread) and ws_thread.is_alive())):
                print("PushBullet WebSocket 스레드 종료 감지 - 재연결 시도...")
                await start_pushbullet_websocket()
        except Exception as e:
            print(f"PushBullet 모니터링 오류: {e}")
            await asyncio.sleep(60)  # 오류 발생 시 1분 대기
def convert_time(seconds):
    hours = minutes = 0
    if seconds >= 3600:
        hours, seconds = divmod(seconds, 3600)
    if seconds >= 60:
        minutes, seconds = divmod(seconds, 60)
    time_format = f"{hours}시간{minutes}분{seconds}초"
    return time_format


class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.persistant_modals_added = False
        self.persistant_views_added = False
    async def auto_post_vending_machine(self):
        try:
            for channel_id in AUTO_VENDING_CHANNEL_IDS:
                channel = self.get_channel(channel_id)
                if channel:
                    try:
                        async for msg in channel.history(limit=None):
                            try:
                                if msg.author == self.user or msg.author.id == self.user.id:
                                    await msg.delete()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    embed = nextcord.Embed(description=VENDING_MACHINE_DESCRIPTION, color=0xfffffe)
                    if VENDING_MACHINE_IMAGE_ENABLED:
                        embed.set_image(url=VENDING_MACHINE_IMAGE_URL)
                    await channel.send(embed=embed, view=ProductListView(guild_id=channel.guild.id if channel.guild else None))
        except Exception as e:
            print(f"자동 자판기 게시 오류: {e}")


bot = Bot(command_prefix="!", intents=nextcord.Intents.all(), help_command=None)


class BankRequestApproveView(nextcord.ui.View):
    def __init__(self, user_id: int, amount: int, depositor_name: str, channel_id: int = None):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.amount = amount
        self.depositor_name = depositor_name
        self.channel_id = channel_id
        self.user_message_id = None
    def _is_admin(self, interaction: nextcord.Interaction) -> bool:
        return interaction.user.id in admin_ids
    async def _approve_common(self, interaction: nextcord.Interaction, use_multiplier: bool):
        if not self._is_admin(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        try:
            guild_id = interaction.guild.id if interaction.guild else list(bot.guilds)[0].id
            credited_amount = self.amount
            
            credited_amount = apply_reseller_bonus_to_charge(credited_amount, self.user_id, interaction.guild)
            
            user_data = get_user_data(guild_id, self.user_id)
            user_data['balance'] = safe_add(user_data['balance'], credited_amount)
            update_user_data(guild_id, self.user_id, user_data)
            
            def normalize_depositor_name(name: str) -> str:
                normalized = re.sub(r"[^가-힣]", "", name)
                bank_words = ["입출금통장", "통장", "계좌", "입금", "출금"]
                for word in bank_words:
                    normalized = normalized.replace(word, "")
                return normalized.strip() if normalized.strip() else name
            
            clean_depositor = normalize_depositor_name(self.depositor_name)
            add_deposit_record(guild_id, self.user_id, credited_amount, method="계좌이체", depositor_name=clean_depositor)
            member = bot.get_user(self.user_id)
            if member:
                try:
                    dm = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
                    dm.add_field(name="입금자명", value=clean_depositor, inline=True)
                    if credited_amount > self.amount:
                        dm.add_field(name="입금 금액", value=f"{self.amount:,}원", inline=True)
                        dm.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - self.amount:,}원", inline=True)
                    dm.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
                    dm.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
                    await member.send(embed=dm)
                except:
                    pass
            confirm = nextcord.Embed(title="승인되었습니다", color=0x2ecc71)
            confirm.add_field(name="입금자명", value=clean_depositor, inline=True)
            if credited_amount > self.amount:
                confirm.add_field(name="입금 금액", value=f"{self.amount:,}원", inline=True)
                confirm.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - self.amount:,}원", inline=True)
            confirm.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
            confirm.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
            confirm.add_field(name="사용자", value=f"<@{self.user_id}>", inline=False)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=confirm)
                else:
                    await interaction.followup.send(embed=confirm)
            except (nextcord.errors.NotFound, nextcord.errors.HTTPException):
                pass
            
            try:
                charge_request_channel = bot.get_channel(CHARGE_REQUEST_CHANNEL_ID)
                if charge_request_channel:
                    request_confirm = nextcord.Embed(title="승인되었습니다", color=0x2ecc71)
                    request_confirm.add_field(name="입금자명", value=clean_depositor, inline=True)
                    if credited_amount > self.amount:
                        request_confirm.add_field(name="입금 금액", value=f"{self.amount:,}원", inline=True)
                        request_confirm.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - self.amount:,}원", inline=True)
                    request_confirm.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
                    request_confirm.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
                    request_confirm.add_field(name="사용자", value=f"<@{self.user_id}>", inline=False)
                    await charge_request_channel.send(embed=request_confirm)
            except Exception:
                pass
            except (nextcord.errors.NotFound, nextcord.errors.HTTPException):
                pass
            for child in self.children:
                if isinstance(child, nextcord.ui.Button):
                    child.disabled = True
            try:
                await interaction.message.edit(view=self)
            except Exception:
                pass
            if self.user_id in PENDING_CHARGES:
                try:
                    del PENDING_CHARGES[self.user_id]
                except Exception:
                    pass
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"승인 중 오류: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"승인 중 오류: {e}", ephemeral=True)
            except (nextcord.errors.NotFound, nextcord.errors.HTTPException):
                pass
    @nextcord.ui.button(label="승인", style=nextcord.ButtonStyle.secondary, custom_id="bank_req_approve")
    async def approve_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await self._approve_common(interaction, use_multiplier=False)
    @nextcord.ui.button(label="배수승인", style=nextcord.ButtonStyle.secondary, custom_id="bank_req_approve_multi")
    async def approve_multi_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not self._is_admin(interaction):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(MultiApprovalModal(self.user_id, self.amount, self.depositor_name))




class ProductBuyView(nextcord.ui.View):
    def __init__(self, product_data, guilid):
        super().__init__(timeout=None)
        self.product_data = product_data
        self.guildid = guilid
    @nextcord.ui.button(emoji="✅", style=nextcord.ButtonStyle.secondary, custom_id="button_3_1")
    async def button_callback1(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        user_data = get_user_data(self.guildid, interaction.user.id)
        products = get_products_from_stock_folder(self.guildid)
        
        product_name = self.product_data[0]
        
        if product_name not in products:
            embed = nextcord.Embed(title="⛔ㆍ오류", color=0xff0000)
            embed.add_field(name="", value="제품을 찾을 수 없습니다.", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        product_info = products[product_name]
        
        try:
            quantity = validate_positive_int(self.product_data[1], MAX_QUANTITY)
    
            unit_price = product_info['price']
            if unit_price <= 0:
                embed = nextcord.Embed(title="⛔ㆍ오류", color=0xff0000)
                embed.add_field(name="", value="제품 가격이 올바르지 않습니다.", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            total_price = safe_multiply(unit_price, quantity)
            
            if quantity <= 0:
                embed = nextcord.Embed(title="⛔ㆍ오류", color=0xff0000)
                embed.add_field(name="", value="수량은 1개 이상이어야 합니다.", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            if total_price <= 0:
                embed = nextcord.Embed(title="⛔ㆍ오류", color=0xff0000)
                embed.add_field(name="", value="가격이 올바르지 않습니다.", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
        except ValueError as e:
            embed = nextcord.Embed(title="⛔ㆍ오류", color=0xff0000)
            embed.add_field(name="", value=f"데이터 검증 오류: {str(e)}", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        current_stock = get_product_stock_count(self.guildid, product_name)
        if current_stock < quantity:
            embed = nextcord.Embed(title="⛔ㆍ재고 부족", color=0xff0000)
            embed.add_field(name="", value=f"재고가 부족해요.\n현재 재고: {current_stock}개, 요청 수량: {quantity}개", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        vip_level = get_vip_level(user_data['total_spent'])
        discount_amount = calculate_discount(total_price, vip_level)
        discount_percent_for_display = VIP_LEVELS[vip_level]['discount']
        final_price = total_price - discount_amount
        
        if final_price <= 0:
            embed = nextcord.Embed(title="⛔ㆍ오류", color=0xff0000)
            embed.add_field(name="", value="최종 결제 금액이 올바르지 않습니다.", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if user_data['balance'] >= final_price:
            try:
                user_data['balance'] = safe_add(user_data['balance'], -final_price)
                user_data['total_spent'] = safe_add(user_data['total_spent'], final_price)
            except ValueError as e:
                embed = nextcord.Embed(title="⛔ㆍ오류", color=0xff0000)
                embed.add_field(name="", value=f"계산 오류가 발생했습니다: {str(e)}", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            new_vip_level = get_vip_level(user_data['total_spent'])
            user_data['vip_level'] = new_vip_level
            
            update_user_data(self.guildid, interaction.user.id, user_data)
            
            purchased_items = remove_product_stock(self.guildid, product_name, quantity)
            add_purchase_log(self.guildid, interaction.user.id, product_name, quantity, total_price, discount_amount)
            if purchased_items:
                items_content = "\n".join(purchased_items)
                items_file = nextcord.File(fp=io.BytesIO(items_content.encode('utf-8')), filename=f"{product_name}_구매내역.txt")
                
                embed = nextcord.Embed(title="✅ㆍ구매 성공", color=0xfffffe)
                embed.add_field(name="제품", value=f"- {product_name} {quantity}개", inline=False)
                embed.add_field(name="구매한 아이템", value="첨부된 텍스트 파일을 확인하세요", inline=False)
                
                if discount_amount > 0:
                    embed.add_field(name="할인", value=f"할인: {discount_amount:,}원 ({discount_percent_for_display}%)", inline=False)
                embed.add_field(name="결제 금액", value=f"{final_price:,}원", inline=False)
                embed.timestamp = datetime.datetime.now()
                await interaction.response.send_message(embed=embed, file=items_file, ephemeral=False)
            else:
                embed = nextcord.Embed(title="✅ㆍ구매 성공", color=0xfffffe)
                embed.add_field(name="제품", value=f"- {product_name} {quantity}개", inline=False)
                embed.add_field(name="구매한 아이템", value="재고가 없습니다", inline=False)
                
                if discount_amount > 0:
                    embed.add_field(name="할인", value=f"할인: {discount_amount:,}원 ({discount_percent_for_display}%)", inline=False)
                embed.add_field(name="결제 금액", value=f"{final_price:,}원", inline=False)
                embed.timestamp = datetime.datetime.now()
                await interaction.response.send_message(embed=embed, ephemeral=False)
            member = bot.get_guild(self.guildid).get_member(interaction.user.id)
            embedVar = nextcord.Embed(
                title="🛒 구매 완료",
                description=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n**{interaction.user.name}**님의 구매가 완료되었습니다!\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=0x00ff00
            )
            
            embedVar.add_field(
                name="📦 구매 제품",
                value=f"```\n{product_name} × {quantity}개\n```",
                inline=True
            )
            
            if discount_amount > 0:
                embedVar.add_field(
                    name="💰 결제 금액",
                    value=f"```\n{final_price:,}원\n(할인: {discount_amount:,}원)\n```",
                    inline=True
                )
            else:
                embedVar.add_field(
                    name="💰 결제 금액",
                    value=f"```\n{final_price:,}원\n```",
                    inline=True
                )
            
            embedVar.add_field(
                name="⏰ 구매 시간",
                value=f"<t:{int(datetime.datetime.now().timestamp())}:R>",
                inline=True
            )
           
            embedVar.set_thumbnail(url=interaction.user.display_avatar.url)
            embedVar.set_footer(text=f"구매자: {interaction.user.name} • ID: {interaction.user.id}", icon_url=interaction.user.display_avatar.url)
            embedVar.timestamp = datetime.datetime.now()
            
            try:
                review_dm_embed = nextcord.Embed(title="⭐ 후기 작성", color=0xffd700)
                review_dm_embed.add_field(name="구매 완료", value=f"**{product_name}** 구매가 완료되었습니다!", inline=False)
                review_dm_embed.add_field(name="후기 작성 보상", value="후기를 작성하시면 **1000원**이 지급됩니다! (계정당 1회만 지급)", inline=False)
                review_dm_embed.add_field(name="후기 작성 방법", value="아래 버튼에서 평점을 선택하고 후기를 작성해주세요.", inline=False)
                await interaction.user.send(embed=review_dm_embed, view=ReviewView(interaction.user.id, product_name))
            except Exception:
                pass
            
            e_channel = bot.get_channel(PURCHASE_LOG_CHANNEL_ID)
            if e_channel:
                message = await e_channel.send(embed=embedVar)
                await message.add_reaction("❤️")
            admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
            if admin_channel:
                admin_embed = nextcord.Embed(title="🛒 관리자 구매 로그", color=0xffd700)
                admin_embed.add_field(name="구매자", value=f"<@{interaction.user.id}> ({interaction.user.name})", inline=True)
                admin_embed.add_field(name="제품", value=f"{product_name} {quantity}개", inline=True)
                admin_embed.add_field(name="결제금액", value=f"{final_price:,}원", inline=True)
                admin_embed.add_field(name="할인", value=f"{discount_amount:,}원", inline=True)
                admin_embed.add_field(name="구매 시간", value=f"<t:{int(datetime.datetime.now().timestamp())}:F>", inline=True)
                
                if purchased_items:
                    items_text = "\n".join(purchased_items)
                    safe_add_field(admin_embed, "📦 구매한 아이템", f"```\n{items_text}\n```", inline=False)
                else:
                    admin_embed.add_field(name="📦 구매한 아이템", value="```\n재고가 없습니다\n```", inline=False)
                
                await admin_channel.send(embed=admin_embed)
            role_id = get_role_id_by_vip_level(new_vip_level)
            role = bot.get_guild(self.guildid).get_role(role_id)
            if role:
                await member.add_roles(role)
            self.stop()
        else:
            embed = nextcord.Embed(title="⛔ㆍ잔액 부족", color=0xff0000)
            embed.add_field(name="",
                            value=f"- 잔액이 부족해요.\n- **{interaction.user.name}**님의 잔액은 **{user_data['balance']:,}**원 입니다.\n- 충전 후 다시 시도해주세요.",
                            inline=False)
            embed.timestamp = datetime.datetime.now()
            await interaction.response.send_message(embed=embed, ephemeral=True)
    @nextcord.ui.button(emoji="❌", style=nextcord.ButtonStyle.secondary, custom_id="button_3_2")
    async def button_callback2(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        embed = nextcord.Embed(title="⛔ㆍ구매 취소", color=0xff0000)
        embed.add_field(name="", value="구매가 취소되었어요.", inline=False)
        embed.timestamp = datetime.datetime.now()
        await interaction.response.send_message(embed=embed, ephemeral=False)
        self.stop()
def save_user_data(user_data):
    try:
        os.makedirs('data', exist_ok=True)
        with open('data/user.json', 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"사용자 데이터 저장 오류: {e}")
def load_user_data():
    try:
        if os.path.exists('data/user.json'):
            with open('data/user.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"사용자 데이터 로드 오류: {e}")
        return {}
def save_buy_history(buy_data):
    try:
        os.makedirs('data', exist_ok=True)
        with open('data/buy.json', 'w', encoding='utf-8') as f:
            json.dump(buy_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"구매 내역 저장 오류: {e}")
def load_buy_history():
    try:
        if os.path.exists('data/buy.json'):
            with open('data/buy.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"구매 내역 로드 오류: {e}")
        return []

def save_deposit_history(deposit_data):
    try:
        os.makedirs('data', exist_ok=True)
        with open('data/deposit.json', 'w', encoding='utf-8') as f:
            json.dump(deposit_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"충전 내역 저장 오류: {e}")
def load_deposit_history():
    try:
        if os.path.exists('data/deposit.json'):
            with open('data/deposit.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"충전 내역 로드 오류: {e}")
        return []

def save_coupons(coupons_data):
    try:
        os.makedirs('data', exist_ok=True)
        with open('data/coupons.json', 'w', encoding='utf-8') as f:
            json.dump(coupons_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"쿠폰 데이터 저장 오류: {e}")

def load_coupons():
    try:
        if os.path.exists('data/coupons.json'):
            with open('data/coupons.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"쿠폰 데이터 로드 오류: {e}")
        return {}

def generate_coupon_code():
    """쿠폰 코드 생성: LEVELUP-XXXXX-XX 형식"""
    import random
    part1 = random.randint(10000, 99999)
    part2 = random.randint(10, 99)
    return f"LEVELUP-{part1}-{part2}"

# 쿠폰 데이터 초기화 (함수 정의 후)
COUPONS = load_coupons()  # 쿠폰 데이터: {coupon_code: {"amount": 금액, "used": False, "used_by": None, "created_at": timestamp}}

class ChargeMethodView(nextcord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @nextcord.ui.button(label="계좌이체", emoji="🏦", style=nextcord.ButtonStyle.secondary, custom_id="bank_transfer")
    async def bank_transfer_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await interaction.response.send_modal(BankTransferModal())
class ChargeAmountInputModal(nextcord.ui.Modal):
    def __init__(self):
        super().__init__(
            title="충전 금액 입력",
            custom_id="charge_amount_input",
            timeout=None
        )
        self.amount_field = nextcord.ui.TextInput(
            label=f"충전할 금액을 입력하세요 (최소 {MIN_CHARGE_AMOUNT:,}원)",
            placeholder=str(MIN_CHARGE_AMOUNT),
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="charge_amount"
        )
        self.add_item(self.amount_field)
    async def callback(self, interaction: nextcord.Interaction) -> None:
        if interaction.response.is_done():
            return
            
        try:
            amount = validate_positive_int(self.amount_field.value, MAX_PRICE)
            if amount < MIN_CHARGE_AMOUNT:
                await interaction.response.send_message(f"최소 충전 금액은 {MIN_CHARGE_AMOUNT:,}원입니다.", ephemeral=True)
                return
            if amount > MAX_PRICE:
                await interaction.response.send_message(f"최대 충전 금액은 {MAX_PRICE:,}원입니다.", ephemeral=True)
                return
        except ValueError as e:
            await interaction.response.send_message(f"올바른 금액을 입력해주세요: {str(e)}", ephemeral=True)
            return
        try:
            user = interaction.user
            dm_embed = nextcord.Embed(title="💰ㆍ계좌이체 충전 안내", color=0x00ff00)
            dm_embed.add_field(name="입금 계좌", value=f"**{BANK_ACCOUNT}**", inline=False)
            dm_embed.add_field(name="충전 금액", value=f"**{amount:,}원**", inline=False)
            dm_embed.add_field(name="충전 방법", value="1. 위 계좌로 입금하세요\n2. 입금 후 송금내역 사진을 이 DM에 보내주세요\n3. 관리자가 확인 후 잔액이 충전됩니다", inline=False)
            dm_embed.add_field(name="주의사항", value=f"• 최소 충전 금액: {MIN_CHARGE_AMOUNT:,}원\n• 입금자명과 디스코드 닉네임이 다를 경우 닉네임을 함께 알려주세요", inline=False)
            dm_embed.set_footer(text="송금내역 사진을 보내주시면 관리자가 확인 후 처리해드립니다.")
            
            await user.send(embed=dm_embed)
            await interaction.response.send_message("DM으로 충전 안내를 보내드렸습니다. DM을 확인해주세요.", ephemeral=True)
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("DM 전송에 실패했습니다. DM 설정을 확인해주세요.", ephemeral=True)
                else:
                    await interaction.followup.send("DM 전송에 실패했습니다. DM 설정을 확인해주세요.", ephemeral=True)
            except Exception as e2:
                print(f"충전 모달 오류: {e2}")
class ProductListView(nextcord.ui.View):
    def __init__(self, guild_id=None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        product_btn = nextcord.ui.Button(label="제품", style=nextcord.ButtonStyle.secondary, custom_id="button_4_1")
        product_btn.callback = self.product_button_handler
        self.add_item(product_btn)
        buy_btn = nextcord.ui.Button(label="구매", style=nextcord.ButtonStyle.secondary, custom_id="button_4_2")
        buy_btn.callback = self.handle_buy
        self.add_item(buy_btn)
        charge_btn = nextcord.ui.Button(label="충전", style=nextcord.ButtonStyle.secondary, custom_id="button_4_4")
        charge_btn.callback = self.handle_charge
        self.add_item(charge_btn)
        info_btn = nextcord.ui.Button(label="내정보", style=nextcord.ButtonStyle.secondary, custom_id="button_4_3")
        info_btn.callback = self.handle_myinfo
        self.add_item(info_btn)
    async def product_button_handler(self, interaction: nextcord.Interaction):
        if on_run:
            embed = nextcord.Embed(title="🛍️ㆍ상품 조회", color=0xfffffe)
            embed.add_field(name="", value="조회할 상품의 카테고리를 선택하세요.", inline=False)
            await interaction.response.send_message(embed=embed, view=CategorySelectView(interaction.guild.id), ephemeral=True)
    async def handle_buy(self, interaction: nextcord.Interaction):
        if on_run:
            embed = nextcord.Embed(title="🛒ㆍ구매할 카테고리 선택", color=0xfffffe)
            embed.add_field(name="", value="구매할 상품의 카테고리를 선택하세요.", inline=False)
            await interaction.response.send_message(embed=embed, view=CategorySelectView(interaction.guild.id, is_purchase=True), ephemeral=True)
    async def handle_charge(self, interaction: nextcord.Interaction):
        if on_run:
            embed = nextcord.Embed(title="💰ㆍ충전 방식 선택", color=0x00ff00)
            embed.add_field(name="", value="충전 방식을 선택해주세요.", inline=False)
            await interaction.response.send_message(embed=embed, view=ChargeMethodView(), ephemeral=True)
    async def handle_myinfo(self, interaction: nextcord.Interaction):
        if on_run:
            user_data = get_user_data(interaction.guild.id, interaction.user.id)
            
            level_colors = {
                "유저": 0x808080,
                "구매자": 0x00ff00,
                "리셀러": 0x1abc9c
            }
            
            if is_reseller(interaction.user, interaction.guild):
                display_level = "리셀러"
            elif user_data['total_spent'] == 0:
                display_level = "유저"
            else:
                display_level = "구매자"
            
            color = level_colors.get(display_level, 0x808080)
            
            level_emojis = {
                "유저": "👤",
                "구매자": "🛒",
                "리셀러": "💎"
            }
            
            level_descriptions = {
                "유저": "아직 구매 이력이 없습니다",
                "구매자": "구매자 역할이 지급됩니다",
                "리셀러": "충전 시 20% 추가 충전 혜택"
            }
            
            embed = nextcord.Embed(
                title=f"{level_emojis.get(display_level, '👤')} 내 정보",
                description=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n**{interaction.user.name}**님의 정보입니다\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=color
            )
            
            embed.add_field(
                name="💰 잔액",
                value=f"```\n{user_data['balance']:,}원\n```",
                inline=True
            )
            
            embed.add_field(
                name="📊 등급",
                value=f"```\n{display_level} {level_emojis.get(display_level, '👤')}\n```",
                inline=True
            )
            
            embed.add_field(
                name="💳 총 구매액",
                value=f"```\n{user_data['total_spent']:,}원\n```",
                inline=True
            )
            
            benefit_emoji = "🎁" if display_level == "리셀러" else "✨" if display_level == "구매자" else "📌"
            embed.add_field(
                name=f"{benefit_emoji} 등급 혜택",
                value=f"```\n{level_descriptions.get(display_level, '할인 없음')}\n```",
                inline=False
            )
            
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text=f"ID: {interaction.user.id} • {interaction.guild.name}", icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)
class CategorySelect(nextcord.ui.Select):
    def __init__(self, guilid, is_purchase=False):
        self.is_purchase = is_purchase
        categories = get_categories_from_stock_folder()
        options = []
        
        if categories:
            for category in categories[:25]:
                emoji = get_category_emoji(category)
                label = f"{emoji} {category}" if emoji else category
                options.append(nextcord.SelectOption(label=label, description=f"{category} 카테고리", value=category))
        else:
            options.append(nextcord.SelectOption(label='전체', description='모든 제품', value='all'))
        
        if not options:
            options = [nextcord.SelectOption(label='카테고리가 없습니다', description='제품이 없습니다', value='none')]
            super().__init__(custom_id='category_dropdown', placeholder='선택할 카테고리가 없습니다', min_values=1, max_values=1, options=options, disabled=True)
        else:
            placeholder = '구매할 카테고리를 선택해주세요.' if is_purchase else '조회할 카테고리를 선택해주세요.'
            super().__init__(custom_id='category_dropdown', placeholder=placeholder, min_values=1, max_values=1, options=options)
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.response.is_done():
            return
        
        category = self.values[0]
        
        if category == 'all':
            products = get_products_from_stock_folder(interaction.guild.id)
            embed_title = "🛍️ㆍ전체 상품 목록"
        elif category == 'none':
            if not interaction.response.is_done():
                await interaction.response.send_message("표시할 제품이 없습니다.", ephemeral=True)
            else:
                await interaction.followup.send("표시할 제품이 없습니다.", ephemeral=True)
            return
        else:
            products = get_products_from_category(category)
            embed_title = "🛍️ㆍ제품 목록"
        if not products:
            embed = nextcord.Embed(title=embed_title, color=0xfffffe)
            embed.add_field(name="", value="등록된 상품이 없습니다.", inline=False)
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
            return
        if self.is_purchase:
            purchase_view = ProductSelectView(interaction.guild.id, category)
            embed = ProductListPaginationView.create_embed(products, category, embed_title, 0)
            view = ProductListPaginationView(products, category, embed_title, 0, purchase_view, interaction.guild.id)
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            embed = ProductListPaginationView.create_embed(products, category, embed_title, 0)
            view = ProductListPaginationView(products, category, embed_title, 0, None, interaction.guild.id)
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
class ProductListPaginationView(nextcord.ui.View):
    PRODUCTS_PER_PAGE = 8
    
    def __init__(self, products, category, embed_title, current_page=0, purchase_view=None, guild_id=None):
        super().__init__(timeout=300)
        self.products = products
        self.category = category
        self.embed_title = embed_title
        self.current_page = current_page
        self.purchase_view = purchase_view
        self.guild_id = guild_id
        self.total_pages = (len(products) + self.PRODUCTS_PER_PAGE - 1) // self.PRODUCTS_PER_PAGE if products else 1
        
        if self.purchase_view:
            for item in self.purchase_view.children:
                if isinstance(item, nextcord.ui.Select):
                    self.add_item(item)
        
        if self.current_page > 0:
            prev_btn = nextcord.ui.Button(label="<", style=nextcord.ButtonStyle.secondary, custom_id="product_list_prev")
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)
        
        next_btn = nextcord.ui.Button(label=">", style=nextcord.ButtonStyle.secondary, custom_id="product_list_next")
        next_btn.callback = self.next_page
        self.add_item(next_btn)
    
    @staticmethod
    def create_embed(products, category, embed_title, page=0):
        embed = nextcord.Embed(title=embed_title, color=0xfffffe)
        
        if not products:
            embed.add_field(name="", value="등록된 상품이 없습니다.", inline=False)
            return embed
        
        PRODUCTS_PER_PAGE = 8
        total_pages = (len(products) + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
        start_idx = page * PRODUCTS_PER_PAGE
        end_idx = min(start_idx + PRODUCTS_PER_PAGE, len(products))
        
        products_list = list(products.items())
        products_list.sort(key=lambda x: x[1].get('price', 0))
        
        for i in range(start_idx, end_idx):
            if i >= len(products_list):
                break
            product_name, product_data = products_list[i]
            
            product_emoji = ""
            if category and category != 'all':
                product_emoji = get_product_emoji(category, product_name)
            else:
                for cat in get_categories_from_stock_folder():
                    emoji = get_product_emoji(cat, product_name)
                    if emoji:
                        product_emoji = emoji
                        break
            
            field_name = f"{product_emoji} {product_name}" if product_emoji else product_name
            field_value = f"{product_data['price']:,}원\n재고 {product_data['stock']:,}개"
            embed.add_field(name=field_name, value=field_value, inline=False)
        
        if total_pages > 1:
            embed.set_footer(text=f"페이지 {page + 1} / {total_pages}")
        
        return embed
    
    async def settings_callback(self, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            embed = nextcord.Embed(title="⛔ 권한 없음", color=0xff0000)
            embed.add_field(name="", value="관리자만 설정에 접근할 수 있습니다.", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = nextcord.Embed(title="⚙️ 설정", color=0x00ff00)
        embed.add_field(name="", value="재고 관리 및 설정 메뉴입니다.", inline=False)
        embed.add_field(name="재고 관리", value="재고수정 버튼을 사용하여 재고를 관리하세요.", inline=False)
        embed.add_field(name="카테고리 추가", value="카테고리 추가 버튼을 눌러 새로운 카테고리를 추가합니다.", inline=False)
        embed.add_field(name="제품 추가", value="제품 추가 버튼을 눌러 새로운 제품을 추가합니다.", inline=False)
        embed.add_field(name="가격수정", value="가격수정 버튼을 눌러 제품 가격을 수정합니다.", inline=False)
        embed.add_field(name="재고수정", value="재고수정 버튼을 눌러 제품 재고를 수정합니다.", inline=False)
        await interaction.response.send_message(embed=embed, view=StockManagementView(), ephemeral=True)
    
    async def prev_page(self, interaction: nextcord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            embed = self.create_embed(self.products, self.category, self.embed_title, self.current_page)
            view = ProductListPaginationView(self.products, self.category, self.embed_title, self.current_page, self.purchase_view, self.guild_id)
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.defer()
    
    async def next_page(self, interaction: nextcord.Interaction):
        self.current_page += 1
        if self.current_page >= self.total_pages:
            self.current_page = 0
        embed = self.create_embed(self.products, self.category, self.embed_title, self.current_page)
        view = ProductListPaginationView(self.products, self.category, self.embed_title, self.current_page, self.purchase_view, self.guild_id)
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, nextcord.ui.Button):
                item.disabled = True
class CategorySelectView(nextcord.ui.View):
    def __init__(self, guilid, is_purchase=False):
        super().__init__(timeout=None)
        self.add_item(CategorySelect(guilid, is_purchase))
class ProductSelectView(nextcord.ui.View):
    def __init__(self, guilid, category=None):
        super().__init__(timeout=None)
        self.add_item(ProductSelectSelect(guilid, category))
class ProductSelectSelect(nextcord.ui.Select):
    def __init__(self, guilid, category=None):
        if category and category != 'all':
            products = get_products_from_category(category)
        else:
            products = get_products_from_stock_folder(guilid)
        
        products_list = list(products.items())
        products_list.sort(key=lambda x: x[1].get('price', 0))
        
        options = []
        for product_name, product_data in products_list[:25]:
            product_emoji = ""
            if category and category != 'all':
                product_emoji = get_product_emoji(category, product_name)
            
            label = f"{product_emoji} {product_data['name']}" if product_emoji else product_data['name']
            description = f"{product_data['price']:,}원 | 재고 {product_data['stock']:,}개"
            value = product_name
            options.append(nextcord.SelectOption(label=label, description=description, value=value))
        if not options:
            options = [nextcord.SelectOption(label='상품이 없습니다', description='재고가 없습니다', value='none')]
            super().__init__(custom_id='my_dropdown', placeholder='선택할 상품이 없습니다', min_values=1, max_values=1, options=options, disabled=True)
        else:
            placeholder = '구매하실 제품을 선택해주세요.'
            super().__init__(custom_id='my_dropdown', placeholder=placeholder, min_values=1, max_values=1, options=options)
    async def callback(self, interaction: nextcord.Interaction):
        products = get_products_from_stock_folder(interaction.guild.id)
        product_name = self.values[0]
        
        if product_name not in products:
            await interaction.response.send_message("제품을 찾을 수 없습니다.", ephemeral=True)
            return
            
        product_data = products[product_name]
        if product_data['stock'] == 0:
            await interaction.response.send_message("재고가 부족해요.", ephemeral=True)
            return
        await interaction.response.send_modal(PurChaseInfo(product_data['name'], product_data['stock']))
class ChargeAmountModal(nextcord.ui.Modal):
    def __init__(self, user_id, log_index):
        super().__init__(
            title="충전 금액 입력",
            custom_id="charge_amount",
            timeout=None
        )
        self.user_id = user_id
        self.log_index = log_index
        
        self.amount_field = nextcord.ui.TextInput(
            label="충전할 금액을 입력하세요",
            placeholder="10000",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="charge_amount_input"
        )
        self.add_item(self.amount_field)
    async def callback(self, interaction: nextcord.Interaction):
        try:
            amount = validate_positive_int(self.amount_field.value, MAX_PRICE)
            if amount <= 0:
                await interaction.response.send_message("올바른 금액을 입력해주세요.", ephemeral=True)
                return
        except ValueError as e:
            await interaction.response.send_message(f"숫자만 입력해주세요: {str(e)}", ephemeral=True)
            return
        
        credited_amount = apply_reseller_bonus_to_charge(amount, self.user_id, interaction.guild)
        
        user_data = get_user_data(interaction.guild.id, self.user_id)
        try:
            user_data['balance'] = safe_add(user_data['balance'], credited_amount)
        except ValueError as e:
            embed = nextcord.Embed(title="⛔ㆍ충전 오류", color=0xff0000)
            embed.add_field(name="", value=f"충전 중 오류가 발생했습니다: {str(e)}", inline=False)
            await interaction.response.send_message(embed=embed)
            return
        
        update_user_data(interaction.guild.id, self.user_id, user_data)
        
        update_charge_log_status(interaction.guild.id, self.log_index, "승인됨")
        
        depositor_name = None
        try:
            data = load_json_data(f'guild_{interaction.guild.id}')
            if 'charge_logs' in data and self.log_index < len(data['charge_logs']):
                log_entry = data['charge_logs'][self.log_index]
                depositor_name = log_entry.get('depositor_name')
        except:
            pass
        
        def normalize_depositor_name(name: str) -> str:
            if not name:
                return name
            normalized = re.sub(r"[^가-힣]", "", name)
            bank_words = ["입출금통장", "통장", "계좌", "입금", "출금"]
            for word in bank_words:
                normalized = normalized.replace(word, "")
            return normalized.strip() if normalized.strip() else name
        
        clean_depositor_name = normalize_depositor_name(depositor_name) if depositor_name else None
        
        embed = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
        if clean_depositor_name:
            embed.add_field(name="입금자명", value=clean_depositor_name, inline=True)
        if credited_amount > amount:
            embed.add_field(name="입금 금액", value=f"{amount:,}원", inline=True)
            embed.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - amount:,}원", inline=True)
        embed.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
        embed.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
        await interaction.response.send_message(embed=embed)
        
        try:
            user = await bot.fetch_user(self.user_id)
            dm_embed = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
            if clean_depositor_name:
                dm_embed.add_field(name="입금자명", value=clean_depositor_name, inline=True)
            if credited_amount > amount:
                dm_embed.add_field(name="입금 금액", value=f"{amount:,}원", inline=True)
                dm_embed.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - amount:,}원", inline=True)
            dm_embed.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
            dm_embed.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
            await user.send(embed=dm_embed)
        except:
            pass
class BankTransferModal(nextcord.ui.Modal):
    def __init__(self):
        super().__init__(
            title="계좌이체 충전",
            custom_id="bank_transfer_modal",
            timeout=None
        )
        
        self.depositor_name = nextcord.ui.TextInput(
            label="입금자명을 입력하세요",
            placeholder="예: 홍길동",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="depositor_name"
        )
        self.add_item(self.depositor_name)
        
        self.charge_amount = nextcord.ui.TextInput(
            label="충전할 금액을 입력하세요",
            placeholder="예: 10000",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="charge_amount"
        )
        self.add_item(self.charge_amount)
    async def callback(self, interaction: nextcord.Interaction) -> None:
        if interaction.response.is_done():
            return
            
        depositor_name = self.depositor_name.value
        charge_amount_str = self.charge_amount.value
        
        try:
            charge_amount = int(charge_amount_str)
            if charge_amount < MIN_CHARGE_AMOUNT:
                await interaction.response.send_message(f"최소 충전 금액은 {MIN_CHARGE_AMOUNT:,}원입니다.", ephemeral=True)
                return
            if charge_amount > MAX_PRICE:
                await interaction.response.send_message(f"최대 충전 금액은 {MAX_PRICE:,}원입니다.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("올바른 금액을 입력해주세요.", ephemeral=True)
            return
        
        try:
            PENDING_CHARGES[interaction.user.id] = {
                "amount": charge_amount,
                "depositor_name": depositor_name,
                "timestamp": datetime.datetime.now().timestamp()
            }
            
            user = interaction.user
            
            try:
                dm_embed = nextcord.Embed(title="🏦ㆍ계좌이체 충전 안내", color=0x00ff00)
                dm_embed.add_field(name="계좌 정보", value=f"**{BANK_ACCOUNT}**", inline=False)
                dm_embed.add_field(name="충전 금액", value=f"**{charge_amount:,}원**", inline=True)
                dm_embed.add_field(name="입금자명", value=f"**{depositor_name}**", inline=True)
                dm_embed.add_field(name="충전 방법", value="위 계좌로 입금하세요. 입금 확인 시 자동 승인됩니다.", inline=False)
                dm_embed.timestamp = datetime.datetime.now()
                await user.send(embed=dm_embed)
            except Exception:
                pass
            
            view = BankRequestApproveView(user.id, charge_amount, depositor_name, interaction.channel.id if interaction.channel else None)
            
            try:
                req_channel = bot.get_channel(BANK_REQUEST_CHANNEL_ID)
                if req_channel:
                    import random
                    rand_code = random.randint(100000, 999999)
                    request_embed = nextcord.Embed(title="💸 충전요청", color=0x00b894)
                    request_embed.add_field(name="사용자이름", value=user.name, inline=True)
                    request_embed.add_field(name="입금자명", value=depositor_name, inline=True)
                    request_embed.add_field(name="금액", value=f"{charge_amount:,}원", inline=True)
                    request_embed.add_field(name="랜덤값", value=str(rand_code), inline=True)
                    request_msg = await req_channel.send(embed=request_embed, view=view)
                    PENDING_CHARGES[interaction.user.id]["message_id"] = request_msg.id
            except Exception as ex:
                print(f"BANK_REQUEST 채널 전송 오류: {ex}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message("DM으로 충전 안내를 보내드렸습니다. DM을 확인해주세요.", ephemeral=True)
            else:
                await interaction.followup.send("DM으로 충전 안내를 보내드렸습니다. DM을 확인해주세요.", ephemeral=True)
        
        except Exception as e:
            error_embed = nextcord.Embed(title="❌ 오류 발생", color=0xff0000)
            error_embed.add_field(name="오류", value="충전 안내 처리 중 오류가 발생했습니다.", inline=False)
            
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
            else:
                try:
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                except Exception:
                    pass
class MultiApprovalModal(nextcord.ui.Modal):
    def __init__(self, user_id, original_amount, depositor_name=None):
        super().__init__(
            title="배수 승인 금액",
            custom_id="multi_approval",
            timeout=None
        )
        self.user_id = user_id
        self.original_amount = original_amount
        self.depositor_name = depositor_name
        
        self.amount_field = nextcord.ui.TextInput(
            label="승인할 금액을 입력하세요",
            placeholder=f"요청 금액: {original_amount:,}원",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="multi_amount"
        )
        self.add_item(self.amount_field)
    
    async def callback(self, interaction: nextcord.Interaction) -> None:
        if interaction.response.is_done():
            return
        
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 기능입니다.", ephemeral=True)
            return
        
        try:
            amount = validate_positive_int(self.amount_field.value, MAX_PRICE)
            
            if amount <= 0:
                await interaction.response.send_message("금액은 0보다 커야 합니다.", ephemeral=True)
                return
            
            if amount > MAX_PRICE:
                await interaction.response.send_message(f"금액은 {MAX_PRICE:,}원을 초과할 수 없습니다.", ephemeral=True)
                return
            
            user = bot.get_user(self.user_id)
            if user:
                credited_amount = apply_reseller_bonus_to_charge(amount, self.user_id, interaction.guild)
                
                user_data = get_user_data(interaction.guild.id, self.user_id)
                user_data['balance'] = safe_add(user_data['balance'], credited_amount)
                update_user_data(interaction.guild.id, self.user_id, user_data)
                
                depositor_name = self.depositor_name
                if not depositor_name and self.user_id in PENDING_CHARGES:
                    depositor_name = PENDING_CHARGES[self.user_id].get('depositor_name')
                
                add_deposit_record(interaction.guild.id, self.user_id, credited_amount, "계좌이체 (배수 승인)", None, depositor_name=depositor_name)
                
                embed = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
                if depositor_name:
                    embed.add_field(name="입금자명", value=depositor_name, inline=True)
                if credited_amount > amount:
                    embed.add_field(name="입금 금액", value=f"{amount:,}원", inline=True)
                    embed.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - amount:,}원", inline=True)
                embed.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
                embed.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
                await user.send(embed=embed)
            
            admin_embed = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
            depositor_name = self.depositor_name
            if not depositor_name and self.user_id in PENDING_CHARGES:
                depositor_name = PENDING_CHARGES[self.user_id].get('depositor_name')
            if depositor_name:
                admin_embed.add_field(name="입금자명", value=depositor_name, inline=True)
            if credited_amount > amount:
                admin_embed.add_field(name="입금 금액", value=f"{amount:,}원", inline=True)
                admin_embed.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - amount:,}원", inline=True)
            admin_embed.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
            user_data = get_user_data(interaction.guild.id, self.user_id)
            admin_embed.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
            admin_embed.set_footer(text=f"관리자: {interaction.user.name}")
            admin_embed.timestamp = datetime.datetime.now()
            
            await interaction.response.send_message(embed=admin_embed)
            
            if self.user_id in PENDING_CHARGES:
                try:
                    del PENDING_CHARGES[self.user_id]
                except Exception:
                    pass
            
        except ValueError:
            await interaction.response.send_message("올바른 금액을 입력해주세요.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"배수 승인 처리 중 오류가 발생했습니다: {e}", ephemeral=True)

class ManualApprovalModal(nextcord.ui.Modal):
    def __init__(self, user_id, original_amount):
        super().__init__(
            title="수동 승인 금액",
            custom_id="manual_approval",
            timeout=None
        )
        self.user_id = user_id
        self.original_amount = original_amount
        
        self.amount_field = nextcord.ui.TextInput(
            label="승인할 금액을 입력하세요",
            placeholder=f"요청 금액: {original_amount:,}원",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="manual_amount"
        )
        self.add_item(self.amount_field)
    async def callback(self, interaction: nextcord.Interaction) -> None:
        if interaction.response.is_done():
            return
            
        try:
            amount = validate_positive_int(self.amount_field.value, MAX_PRICE)
            
            if amount <= 0:
                await interaction.response.send_message("금액은 0보다 커야 합니다.", ephemeral=True)
                return
                
            if amount > MAX_PRICE:
                await interaction.response.send_message(f"금액은 {MAX_PRICE:,}원을 초과할 수 없습니다.", ephemeral=True)
                return
            
            credited_amount = apply_reseller_bonus_to_charge(amount, self.user_id, interaction.guild)
            
            user_data = get_user_data(interaction.guild.id, self.user_id)
            user_data['balance'] = safe_add(user_data['balance'], credited_amount)
            update_user_data(interaction.guild.id, self.user_id, user_data)
            
            depositor_name = None
            if self.user_id in PENDING_CHARGES:
                depositor_name = PENDING_CHARGES[self.user_id].get('depositor_name')
            
            add_deposit_record(interaction.guild.id, self.user_id, credited_amount, "계좌이체 (수동 승인)", None, depositor_name=depositor_name)
            
            user = bot.get_user(self.user_id)
            if user:
                embed = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
                if depositor_name:
                    embed.add_field(name="입금자명", value=depositor_name, inline=True)
                if credited_amount > amount:
                    embed.add_field(name="입금 금액", value=f"{amount:,}원", inline=True)
                    embed.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - amount:,}원", inline=True)
                embed.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
                embed.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
                await user.send(embed=embed)
            
            admin_embed = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
            if depositor_name:
                admin_embed.add_field(name="입금자명", value=depositor_name, inline=True)
            if credited_amount > amount:
                admin_embed.add_field(name="입금 금액", value=f"{amount:,}원", inline=True)
                admin_embed.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - amount:,}원", inline=True)
            admin_embed.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
            admin_embed.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
            admin_embed.set_footer(text=f"관리자: {interaction.user.name}")
            admin_embed.timestamp = datetime.datetime.now()
            
            await interaction.response.send_message(embed=admin_embed)
            
        except ValueError:
            await interaction.response.send_message("올바른 금액을 입력해주세요.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"수동 승인 처리 중 오류가 발생했습니다: {e}", ephemeral=True)
class RejectReasonModal(nextcord.ui.Modal):
    def __init__(self, user_id, amount):
        super().__init__(
            title="충전 거절 사유",
            custom_id="reject_reason",
            timeout=None
        )
        self.user_id = user_id
        self.amount = amount
        
        self.reason_field = nextcord.ui.TextInput(
            label="거절 사유를 입력하세요",
            placeholder="예: 송금내역이 불분명합니다",
            required=True,
            style=nextcord.TextInputStyle.paragraph,
            custom_id="reject_reason_text"
        )
        self.add_item(self.reason_field)
    async def callback(self, interaction: nextcord.Interaction) -> None:
        if interaction.response.is_done():
            return
            
        reason = self.reason_field.value
        
        try:
            user = bot.get_user(self.user_id)
            if user:
                embed = nextcord.Embed(title="❌ㆍ충전 거절", color=0xff0000)
                embed.add_field(name="요청 금액", value=f"**{self.amount:,}원**", inline=True)
                embed.add_field(name="거절 사유", value=reason, inline=False)
                embed.timestamp = datetime.datetime.now()
                
                await user.send(embed=embed)
            
            admin_embed = nextcord.Embed(title="❌ㆍ충전 거절 완료", color=0xff0000)
            admin_embed.add_field(name="대상 사용자", value=f"<@{self.user_id}>", inline=True)
            admin_embed.add_field(name="요청 금액", value=f"**{self.amount:,}원**", inline=True)
            admin_embed.add_field(name="거절 사유", value=reason, inline=False)
            admin_embed.set_footer(text=f"관리자: {interaction.user.name}")
            admin_embed.timestamp = datetime.datetime.now()
            
            await interaction.response.send_message(embed=admin_embed)
            
        except Exception as e:
            await interaction.response.send_message(f"거절 처리 중 오류가 발생했습니다: {e}", ephemeral=True)
class ChargeApprovalView(nextcord.ui.View):
    def __init__(self, user_id, amount, receipt_image=None):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.amount = amount
        self.receipt_image = receipt_image
    @nextcord.ui.button(label="승인", emoji="✅", style=nextcord.ButtonStyle.secondary, custom_id="approve_charge")
    async def approve_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 기능입니다.", ephemeral=True)
            return
        
        try:
            if self.amount <= 0:
                await interaction.response.send_message("승인할 금액이 올바르지 않습니다.", ephemeral=True)
                return
        
            user = bot.get_user(self.user_id)
            if user:
                credited_amount = apply_reseller_bonus_to_charge(self.amount, self.user_id, interaction.guild)
                
                user_data = get_user_data(interaction.guild.id, self.user_id)
                user_data['balance'] = safe_add(user_data['balance'], credited_amount)
                update_user_data(interaction.guild.id, self.user_id, user_data)
                
                depositor_name = None
                if self.user_id in PENDING_CHARGES:
                    depositor_name = PENDING_CHARGES[self.user_id].get('depositor_name')
                
                add_deposit_record(interaction.guild.id, self.user_id, credited_amount, "계좌이체", self.receipt_image, depositor_name=depositor_name)
                
                embed = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
                if depositor_name:
                    embed.add_field(name="입금자명", value=depositor_name, inline=True)
                if credited_amount > self.amount:
                    embed.add_field(name="입금 금액", value=f"{self.amount:,}원", inline=True)
                    embed.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - self.amount:,}원", inline=True)
                embed.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
                embed.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
                await user.send(embed=embed)
                
                admin_embed = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
                if depositor_name:
                    admin_embed.add_field(name="입금자명", value=depositor_name, inline=True)
                if credited_amount > self.amount:
                    admin_embed.add_field(name="입금 금액", value=f"{self.amount:,}원", inline=True)
                    admin_embed.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - self.amount:,}원", inline=True)
                admin_embed.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
                admin_embed.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
                admin_embed.set_footer(text=f"관리자: {interaction.user.name}")
                admin_embed.timestamp = datetime.datetime.now()
                
                await interaction.response.send_message(embed=admin_embed)
            else:
                await interaction.response.send_message("사용자를 찾을 수 없습니다.", ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"승인 처리 중 오류가 발생했습니다: {e}", ephemeral=True)
    @nextcord.ui.button(label="2배 승인", emoji="💰", style=nextcord.ButtonStyle.secondary, custom_id="approve_2x")
    async def approve_2x_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 기능입니다.", ephemeral=True)
            return
        
        depositor_name = None
        if self.user_id in PENDING_CHARGES:
            depositor_name = PENDING_CHARGES[self.user_id].get('depositor_name')
        
        await interaction.response.send_modal(MultiApprovalModal(self.user_id, self.amount, depositor_name))
    @nextcord.ui.button(label="3배 승인", emoji="💎", style=nextcord.ButtonStyle.secondary, custom_id="approve_3x")
    async def approve_3x_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 기능입니다.", ephemeral=True)
            return
        
        depositor_name = None
        if self.user_id in PENDING_CHARGES:
            depositor_name = PENDING_CHARGES[self.user_id].get('depositor_name')
        
        await interaction.response.send_modal(MultiApprovalModal(self.user_id, self.amount, depositor_name))
    @nextcord.ui.button(label="수동 승인", emoji="✏️", style=nextcord.ButtonStyle.secondary, custom_id="manual_approve")
    async def manual_approve_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 기능입니다.", ephemeral=True)
            return
            
        await interaction.response.send_modal(ManualApprovalModal(self.user_id, self.amount))
    @nextcord.ui.button(label="거절", emoji="❌", style=nextcord.ButtonStyle.secondary, custom_id="reject_charge")
    async def reject_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 기능입니다.", ephemeral=True)
            return
            
        await interaction.response.send_modal(RejectReasonModal(self.user_id, self.amount))

class ImageChargeApprovalView(nextcord.ui.View):
    def __init__(self, user_id, amount, log_index, depositor_name, image_url):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.amount = amount
        self.log_index = log_index
        self.depositor_name = depositor_name
        self.image_url = image_url
    
    @nextcord.ui.button(label="승인", emoji="✅", style=nextcord.ButtonStyle.secondary, custom_id="image_approve")
    async def approve_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 기능입니다.", ephemeral=True)
            return
        
        try:
            credited_amount = apply_reseller_bonus_to_charge(self.amount, self.user_id, interaction.guild)
            
            user_data = get_user_data(interaction.guild.id, self.user_id)
            user_data['balance'] = safe_add(user_data['balance'], credited_amount)
            update_user_data(interaction.guild.id, self.user_id, user_data)
            
            def normalize_depositor_name(name: str) -> str:
                if not name:
                    return name
                normalized = re.sub(r"[^가-힣]", "", name)
                bank_words = ["입출금통장", "통장", "계좌", "입금", "출금"]
                for word in bank_words:
                    normalized = normalized.replace(word, "")
                return normalized.strip() if normalized.strip() else name
            
            clean_depositor = normalize_depositor_name(self.depositor_name)
            add_deposit_record(interaction.guild.id, self.user_id, credited_amount, "계좌이체", self.image_url, depositor_name=clean_depositor)
            update_charge_log_status(interaction.guild.id, self.log_index, "승인됨")
            
            try:
                user = bot.get_user(self.user_id)
                if user:
                    embed = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
                    embed.add_field(name="입금자명", value=clean_depositor, inline=True)
                    if credited_amount > self.amount:
                        embed.add_field(name="입금 금액", value=f"{self.amount:,}원", inline=True)
                        embed.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - self.amount:,}원", inline=True)
                    embed.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
                    embed.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
                    await user.send(embed=embed)
            except Exception:
                pass
            
            admin_embed = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
            admin_embed.add_field(name="입금자명", value=self.depositor_name, inline=True)
            if credited_amount > self.amount:
                admin_embed.add_field(name="입금 금액", value=f"{self.amount:,}원", inline=True)
                admin_embed.add_field(name="리셀러 추가 충전 (20%)", value=f"+{credited_amount - self.amount:,}원", inline=True)
            admin_embed.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
            admin_embed.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
            admin_embed.set_footer(text=f"관리자: {interaction.user.name}")
            admin_embed.timestamp = datetime.datetime.now()
            
            await interaction.response.send_message(embed=admin_embed)
            
            for child in self.children:
                if isinstance(child, nextcord.ui.Button):
                    child.disabled = True
            try:
                await interaction.message.edit(view=self)
            except Exception:
                pass
            
            if self.user_id in PENDING_CHARGES:
                try:
                    del PENDING_CHARGES[self.user_id]
                except Exception:
                    pass
                    
        except Exception as e:
            await interaction.response.send_message(f"승인 처리 중 오류가 발생했습니다: {e}", ephemeral=True)
    
    @nextcord.ui.button(label="거절", emoji="❌", style=nextcord.ButtonStyle.secondary, custom_id="image_reject")
    async def reject_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 기능입니다.", ephemeral=True)
            return
        
        try:
            await interaction.response.send_modal(RejectReasonModal(self.user_id, self.amount))
            
            try:
                update_charge_log_status(interaction.guild.id, self.log_index, "거절됨")
            except:
                pass
            
            try:
                if self.user_id in PENDING_CHARGES:
                    del PENDING_CHARGES[self.user_id]
            except:
                pass
        except Exception as e:
            await interaction.response.send_message(f"거절 처리 중 오류가 발생했습니다: {e}", ephemeral=True)

class TimeoutChargeApprovalView(nextcord.ui.View):
    def __init__(self, user_id, amount, log_index, depositor_name):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.amount = amount
        self.log_index = log_index
        self.depositor_name = depositor_name
    
    @nextcord.ui.button(label="승인", emoji="✅", style=nextcord.ButtonStyle.secondary, custom_id="timeout_approve")
    async def approve_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 기능입니다.", ephemeral=True)
            return
        
        try:
            await interaction.response.send_modal(ChargeAmountModal(self.user_id, self.log_index))
        except Exception as e:
            await interaction.response.send_message(f"승인 처리 중 오류가 발생했습니다: {e}", ephemeral=True)
    
    @nextcord.ui.button(label="거절", emoji="❌", style=nextcord.ButtonStyle.secondary, custom_id="timeout_reject")
    async def reject_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 기능입니다.", ephemeral=True)
            return
        
        try:
            await interaction.response.send_modal(RejectReasonModal(self.user_id, self.amount))
            
            try:
                update_charge_log_status(interaction.guild.id, self.log_index, "거절됨")
            except:
                pass
            
            try:
                if self.user_id in PENDING_CHARGES:
                    del PENDING_CHARGES[self.user_id]
            except:
                pass
        except Exception as e:
            await interaction.response.send_message(f"거절 처리 중 오류가 발생했습니다: {e}", ephemeral=True)

class ReviewView(nextcord.ui.View):
    def __init__(self, user_id, product_name, message_id=None):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.product_name = product_name
        self.message_id = message_id
    
    @nextcord.ui.button(label="1점", emoji="⭐", style=nextcord.ButtonStyle.secondary, custom_id="review_1")
    async def review_1_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("본인만 후기를 작성할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(ReviewModal(1, self.product_name, self.user_id))
    
    @nextcord.ui.button(label="2점", emoji="⭐", style=nextcord.ButtonStyle.secondary, custom_id="review_2")
    async def review_2_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("본인만 후기를 작성할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(ReviewModal(2, self.product_name, self.user_id))
    
    @nextcord.ui.button(label="3점", emoji="⭐", style=nextcord.ButtonStyle.secondary, custom_id="review_3")
    async def review_3_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("본인만 후기를 작성할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(ReviewModal(3, self.product_name, self.user_id))
    
    @nextcord.ui.button(label="4점", emoji="⭐", style=nextcord.ButtonStyle.secondary, custom_id="review_4")
    async def review_4_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("본인만 후기를 작성할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(ReviewModal(4, self.product_name, self.user_id))
    
    @nextcord.ui.button(label="5점", emoji="⭐", style=nextcord.ButtonStyle.secondary, custom_id="review_5")
    async def review_5_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("본인만 후기를 작성할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(ReviewModal(5, self.product_name, self.user_id))

class ReviewModal(nextcord.ui.Modal):
    def __init__(self, rating, product_name, user_id):
        super().__init__(
            title="후기 작성",
            custom_id="review_modal",
            timeout=None
        )
        self.rating = rating
        self.product_name = product_name
        self.user_id = user_id
        
        self.review_field = nextcord.ui.TextInput(
            label="후기를 작성해주세요",
            placeholder="구매 후기를 자유롭게 작성해주세요.",
            required=True,
            style=nextcord.TextInputStyle.paragraph,
            custom_id="review_text"
        )
        self.add_item(self.review_field)
    
    async def callback(self, interaction: nextcord.Interaction) -> None:
        if interaction.response.is_done():
            return
        
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("본인만 후기를 작성할 수 있습니다.", ephemeral=True)
            return
        
        review_text = self.review_field.value.strip()
        if not review_text:
            await interaction.response.send_message("후기 내용을 입력해주세요.", ephemeral=True)
            return
        
        try:
            review_key = f"{self.user_id}"
            if review_key in REVIEWED_USERS:
                await interaction.response.send_message("이미 후기 보상을 받으셨습니다. (계정당 1회만 지급)", ephemeral=True)
                return
            
            review_channel = bot.get_channel(REVIEW_CHANNEL_ID)
            if review_channel:
                stars = "⭐" * self.rating
                review_embed = nextcord.Embed(title="⭐ 구매 후기", color=0xffd700)
                review_embed.add_field(name="구매자", value=f"<@{self.user_id}> ({interaction.user.name})", inline=True)
                review_embed.add_field(name="제품", value=self.product_name, inline=True)
                review_embed.add_field(name="평점", value=f"{stars} ({self.rating}/5)", inline=True)
                review_embed.add_field(name="후기", value=review_text, inline=False)
                review_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                review_embed.set_footer(text=f"작성자: {interaction.user.name} • ID: {self.user_id}")
                review_embed.timestamp = datetime.datetime.now()
                
                await review_channel.send(embed=review_embed)
            
            guild_id = None
            if interaction.guild:
                guild_id = interaction.guild.id
            else:
                if bot.guilds:
                    guild_id = list(bot.guilds)[0].id
            
            if not guild_id:
                await interaction.response.send_message("서버를 찾을 수 없습니다. 서버에서 다시 시도해주세요.", ephemeral=True)
                return
            
            user_data = get_user_data(guild_id, self.user_id)
            user_data['balance'] = safe_add(user_data['balance'], 1000)
            update_user_data(guild_id, self.user_id, user_data)
            
            REVIEWED_USERS.add(review_key)
            
            await interaction.response.send_message(f"후기가 작성되었습니다! 후기 작성 보상으로 10원이 지급되었습니다. (현재 잔액: {user_data['balance']:,}원)", ephemeral=True)
            
            try:
                if interaction.message:
                    disabled_view = nextcord.ui.View(timeout=None)
                    for component in interaction.message.components:
                        for item in component.children:
                            if isinstance(item, nextcord.ui.Button):
                                disabled_btn = nextcord.ui.Button(
                                    label=item.label or "후기 작성 완료",
                                    style=item.style,
                                    emoji=item.emoji if item.emoji else None,
                                    disabled=True,
                                    custom_id=item.custom_id
                                )
                                disabled_view.add_item(disabled_btn)
                    await interaction.message.edit(view=disabled_view)
            except Exception:
                pass
            
        except Exception as e:
            await interaction.response.send_message(f"후기 작성 중 오류가 발생했습니다: {e}", ephemeral=True)

class PurChaseInfo(nextcord.ui.Modal):
    def __init__(self, product_title, invent):
        super().__init__(
            title=f"{product_title}ㆍ제품 구매",
            custom_id="purchase",
            timeout=None
        )
        placeholder_text = f"현재 재고: {invent}개 (최대 {invent}개까지 구매 가능)" if invent > 0 else "재고가 없습니다."
        self.field = nextcord.ui.TextInput(
            label="구매할 수량을 입력해주세요.",
            placeholder=placeholder_text,
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="amont",
        )
        self.add_item(self.field)
        self.product_title = product_title
        self.invent = invent
    async def callback(self, interaction: nextcord.Interaction) -> None:
        if interaction.response.is_done():
            return
        
        try:
            amount = validate_positive_int(self.children[0].value, MAX_QUANTITY)
            if amount <= 0:
                if not interaction.response.is_done():
                    await interaction.response.send_message("수량은 1개 이상이어야 합니다.", ephemeral=True)
                else:
                    await interaction.followup.send("수량은 1개 이상이어야 합니다.", ephemeral=True)
                return
        except ValueError as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"올바른 수량을 입력해주세요: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"올바른 수량을 입력해주세요: {str(e)}", ephemeral=True)
            return
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"정확한 수량을 입력해주세요.\n입력 : {self.children[0].value}", ephemeral=True)
            else:
                await interaction.followup.send(f"정확한 수량을 입력해주세요.\n입력 : {self.children[0].value}", ephemeral=True)
            return
        
        if interaction.guild is None:
            if not interaction.response.is_done():
                await interaction.response.send_message("이 기능은 서버에서만 사용할 수 있습니다.", ephemeral=True)
            else:
                await interaction.followup.send("이 기능은 서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
            
        current_stock = get_product_stock_count(interaction.guild.id, self.product_title)
        if current_stock < amount:
            if not interaction.response.is_done():
                await interaction.response.send_message("⛔ㆍ재고가 부족해요.", ephemeral=True)
            else:
                await interaction.followup.send("⛔ㆍ재고가 부족해요.", ephemeral=True)
            return
            
        products = get_products_from_stock_folder(interaction.guild.id)
        if self.product_title not in products:
            if not interaction.response.is_done():
                await interaction.response.send_message("제품을 찾을 수 없습니다.", ephemeral=True)
            else:
                await interaction.followup.send("제품을 찾을 수 없습니다.", ephemeral=True)
            return
            
        product_data = products[self.product_title]
        user_data = get_user_data(interaction.guild.id, interaction.user.id)
        
        if product_data['price'] <= 0:
            await interaction.response.send_message("제품 가격이 올바르지 않습니다.", ephemeral=True)
            return
        
        try:
            total_price = safe_multiply(product_data['price'], amount)
            if total_price <= 0:
                await interaction.response.send_message("계산된 가격이 올바르지 않습니다.", ephemeral=True)
                return
        except ValueError as e:
            await interaction.response.send_message(f"가격 계산 오류: {str(e)}", ephemeral=True)
            return
        
        vip_level = get_vip_level(user_data['total_spent'])
        discount_amount = calculate_discount(total_price, vip_level)
        discount_percent_for_display = VIP_LEVELS[vip_level]['discount']
        final_price = total_price - discount_amount
        
        if final_price <= 0:
            await interaction.response.send_message("최종 결제 금액이 올바르지 않습니다.", ephemeral=True)
            return
        embed = nextcord.Embed(title="구매 확인", color=0xfffffe)
        name_string = f"{self.product_title} {str(amount)}개"
        embed.add_field(name=f"`{name_string}` - **{total_price:,}원**", value="", inline=False)
        
        if discount_amount > 0:
            embed.add_field(name="할인", value=f"할인: {discount_amount:,}원 ({discount_percent_for_display}%)", inline=False)
            embed.add_field(name="최종 결제 금액", value=f"**{final_price:,}원**", inline=False)
        
        embed.add_field(name="구매하시겠습니까?", value=f"- **{interaction.user.name}**님은 **{user_data['balance']:,}원** 보유중 입니다.",
                        inline=False)
        
        product_data_array = [self.product_title, str(amount), total_price]
        try:
            await interaction.user.send(embed=embed,
                                        view=ProductBuyView(product_data_array, interaction.guild.id))
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("💬ㆍDM을 확인해주세요.", ephemeral=True)
                else:
                    await interaction.followup.send("💬ㆍDM을 확인해주세요.", ephemeral=True)
            except (nextcord.errors.NotFound, nextcord.errors.HTTPException):
                pass
        except nextcord.Forbidden:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("💬ㆍDM을 받을 수 없습니다. DM 설정을 확인해주세요.", ephemeral=True)
                else:
                    await interaction.followup.send("💬ㆍDM을 받을 수 없습니다. DM 설정을 확인해주세요.", ephemeral=True)
            except (nextcord.errors.NotFound, nextcord.errors.HTTPException):
                pass
class anstkd(nextcord.ui.Modal):
    def __init__(self):
        super().__init__(
            title=f"문화상품권 충전",
            custom_id="purchase",
            timeout=None
        )
        self.field = nextcord.ui.TextInput(
            label="상품권 핀번호를 입력해주세요. (-포함)",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="value",
        )
        self.add_item(self.field)
    async def callback(self, interaction: nextcord.Interaction) -> None:
        culture_id = "culture_id"
        culture_pw = "culture_pw"
        
        data2 = {
            'token': '00000000-0000-0000-0000-000000000000',
            'id': culture_id,
            'password': culture_pw,
            'pin': self.children[0].value
        }
        res_data = requests.post("", json=data2).json()
        if res_data["result"]:
            try:
                amount = validate_positive_int(res_data["amount"], MAX_PRICE)
                user_data = get_user_data(interaction.guild.id, interaction.user.id)
                user_data['balance'] = safe_add(user_data['balance'], amount)
                update_user_data(interaction.guild.id, interaction.user.id, user_data)
            except ValueError as e:
                embed = nextcord.Embed(title="⛔ㆍ충전 실패", color=0xff0000)
                embed.add_field(name="", value=f"충전 금액 오류: {str(e)}", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            embed = nextcord.Embed(title="✅ㆍ충전 성공", color=0xfffffe)
            embed.add_field(name=f"`{amount:,}`원 충전에 성공했어요!", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = nextcord.Embed(title="⛔ㆍ충전 실패", color=0xfffffe)
            embed.add_field(name=f"`충전에 실패했어요.", inline=False)
            embed.add_field(name=f"`핀 번호를 다시 확인해주세요.", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
@bot.slash_command(name="자판기", description=f"{SERVICE_NAME} | 자동판매기를 세팅합니다.")
async def callback(interaction: nextcord.Interaction, 채널: nextcord.TextChannel = SlashOption(description="자판기를 보낼 채널", required=True)):
    if on_run:
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return
        
        embed = nextcord.Embed(title="** 👑김갑룡 자판기👑 **", description=VENDING_MACHINE_DESCRIPTION, color=0xfffffe)
        
        await interaction.response.send_message(f"자판기를 <#{채널.id}>에 전송 중입니다...", ephemeral=True)
        
        if VENDING_MACHINE_IMAGE_ENABLED:
            embed.set_image(url=VENDING_MACHINE_IMAGE_URL)
        await 채널.send(embed=embed, view=ProductListView(guild_id=interaction.guild.id))
        
        await interaction.edit_original_message(content=f"자판기가 <#{채널.id}>에 성공적으로 전송되었습니다.")
@bot.slash_command(name="정보", description=f"{SERVICE_NAME} | 서버 정보를 확인합니다.")
async def callback(interaction: nextcord.Interaction):
    if on_run:
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return
        
        embed = nextcord.Embed(title=f"📄ㆍ{interaction.guild.name}", color=0xfffffe)
        embed.add_field(name=f" ",
        value=f"**서버 ID** : `{interaction.guild.id}`\n**서버 이름** : `{interaction.guild.name}`\n**구매 로그** : <#{PURCHASE_LOG_CHANNEL_ID}>\n**충전 로그** : <#{CHARGE_LOG_CHANNEL_ID}>\n**재고 로그** : <#{STOCK_LOG_CHANNEL_ID}>\n**최소충전금** : `{MIN_CHARGE_AMOUNT:,}원`\n**결제 수단** : `계좌이체`",
                                inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
@bot.slash_command(name="도움말", description=f"{SERVICE_NAME} | 명령어 리스트를 확인합니다.")
async def callback(interaction: nextcord.Interaction):
    if on_run:
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return
        
        embed = nextcord.Embed(title=f"📄ㆍ명령어", color=0xfffffe)
        embed.add_field(name=f"슬래시 명령어",
        value=f"- `/정보`\n - 서버 정보를 확인해요.\n- `/자판기`\n - 자동판매기를 세팅해요.\n- `/잔액관리`\n - 유저 잔액을 관리해요.\n- `/내정보`\n - 내 정보를 확인해요.\n- `/재고수정`\n - 재고를 관리해요 (추가/제거/가격수정).\n- `/자동충전토큰`\n - PushBullet 자동충전 토큰을 설정해요.\n- `/계좌설정`\n - 충전 계좌번호를 설정해요.\n- `/관리자설정`\n - 관리자 권한을 부여/제거해요 (최고 관리자 전용).\n- `/리셀러설정`\n - 리셀러 역할을 부여/제거해요.",
                                inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
@bot.slash_command(name="계좌설정", description=f"{SERVICE_NAME} | 충전 계좌번호를 설정합니다.")
async def bank_account_set_command(interaction: nextcord.Interaction, 계좌번호: str = SlashOption(description="계좌번호와 은행명을 입력하세요 (예: 888004408748케이뱅크)", required=True)):
    if on_run:
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return
        
        try:
            if len(계좌번호) > MAX_STRING_LENGTH:
                await interaction.response.send_message(f"계좌번호가 너무 깁니다. (최대 {MAX_STRING_LENGTH}자)", ephemeral=True)
                return
            
            save_bank_account(계좌번호)
            
            global BANK_ACCOUNT
            BANK_ACCOUNT = 계좌번호
            
            embed = nextcord.Embed(title="✅ 계좌 설정 완료", color=0x00ff00)
            embed.add_field(name="설정된 계좌", value=f"**{계좌번호}**", inline=False)
            embed.add_field(name="알림", value="이제 충전 신청 시 이 계좌번호가 사용됩니다.", inline=False)
            embed.set_footer(text=f"관리자: {interaction.user.name}")
            embed.timestamp = datetime.datetime.now()
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            error_embed = nextcord.Embed(title="❌ 오류 발생", color=0xff0000)
            error_embed.add_field(name="오류", value=f"계좌 설정 중 오류가 발생했습니다: {str(e)}", inline=False)
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
@bot.slash_command(name="자동충전토큰", description=f"{SERVICE_NAME} | PushBullet 자동충전 토큰 상태 및 통신을 확인합니다.")
async def pushbullet_token_command(interaction: nextcord.Interaction):
    if on_run:
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        current_status = "✅ 설정됨" if PUSHBULLET_TOKEN else "❌ 설정 안 됨"
        token_preview = ""
        if PUSHBULLET_TOKEN:
            token_preview = f"`{PUSHBULLET_TOKEN[:10]}...`"
        
        api_status = "❌ 테스트 안 됨"
        api_message = ""
        websocket_status = "❌ 연결 안 됨"
        websocket_message = ""
        
        if PUSHBULLET_TOKEN:
            try:
                headers = {
                    "Access-Token": PUSHBULLET_TOKEN,
                    "Content-Type": "application/json"
                }
                response = requests.get("https://api.pushbullet.com/v2/users/me", headers=headers, timeout=5)
                if response.status_code == 200:
                    user_data = response.json()
                    api_status = "✅ 통신 성공"
                    api_message = f"사용자: {user_data.get('name', '알 수 없음')}"
                elif response.status_code == 401:
                    api_status = "❌ 인증 실패"
                    api_message = "토큰이 유효하지 않습니다."
                else:
                    api_status = f"⚠️ 오류 ({response.status_code})"
                    api_message = response.text[:100] if response.text else "알 수 없는 오류"
            except requests.exceptions.Timeout:
                api_status = "❌ 타임아웃"
                api_message = "서버 응답 시간 초과"
            except Exception as e:
                api_status = "❌ 오류"
                api_message = str(e)[:100]
            
            try:
                import sys
                current_module = sys.modules[__name__]
                
                ws_obj = getattr(current_module, 'pushbullet_ws', None)
                ws_thread = getattr(current_module, 'pushbullet_ws_thread', None)
                
                if ws_obj:
                    try:
                        if hasattr(ws_obj, 'sock') and ws_obj.sock:
                            if hasattr(ws_obj.sock, 'connected') and ws_obj.sock.connected:
                                websocket_status = "✅ 연결됨"
                                websocket_message = "WebSocket이 정상적으로 연결되어 있습니다."
                            else:
                                websocket_status = "⚠️ 연결 끊김"
                                websocket_message = "WebSocket 소켓이 있지만 연결이 끊어졌습니다."
                        else:
                            websocket_status = "⚠️ 연결 중"
                            websocket_message = "WebSocket 연결이 진행 중입니다."
                    except:
                        websocket_status = "⚠️ 상태 확인 중"
                        websocket_message = "WebSocket 객체가 있지만 상태를 확인할 수 없습니다."
                elif ws_thread and ws_thread.is_alive():
                    websocket_status = "⚠️ 실행 중"
                    websocket_message = "WebSocket 스레드가 실행 중입니다. 연결 확인 중..."
                else:
                    websocket_status = "❌ 연결 안 됨"
                    websocket_message = "WebSocket이 시작되지 않았습니다. 봇 재시작이 필요할 수 있습니다."
            except Exception as e:
                websocket_status = "❌ 확인 불가"
                websocket_message = f"상태 확인 오류: {str(e)[:50]}"
        else:
            api_status = "❌ 토큰 없음"
            api_message = "토큰이 설정되지 않았습니다."
            websocket_status = "❌ 토큰 없음"
            websocket_message = "토큰이 설정되지 않았습니다."
        
        embed = nextcord.Embed(title="📱 자동 충전 토큰 상태", color=0x00ff00)
        embed.add_field(name="토큰 설정 상태", value=current_status, inline=False)
        if token_preview:
            embed.add_field(name="토큰 미리보기", value=token_preview, inline=False)
        
        embed.add_field(name="API 통신 상태", value=f"{api_status}\n{api_message}", inline=False)
        embed.add_field(name="WebSocket 연결 상태", value=f"{websocket_status}\n{websocket_message}", inline=False)
        
        embed.add_field(
            name="토큰 설정 방법", 
            value="`.env` 파일에 다음을 추가하세요:\n```\nPUSHBULLET_TOKEN=여기에_토큰_입력\n```\n\n1. https://www.pushbullet.com/#settings 접속\n2. Account → Create Access Token 클릭\n3. 생성된 토큰을 복사하여 `.env` 파일에 추가\n4. 봇을 재시작하면 자동으로 적용됩니다.", 
            inline=False
        )
        embed.add_field(
            name="사용 방법",
            value="1. 안드로이드에서 PushBullet 앱 설치\n2. 알림 미러링 활성화\n3. 입금 알림이 자동으로 감지되어 충전됩니다.",
            inline=False
        )
        embed.set_footer(text="토큰을 설정하면 안드로이드 입금 알림이 자동으로 감지됩니다.")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

@bot.slash_command(name="잔액관리", description=f"{SERVICE_NAME} | 유저 잔액을 관리합니다.")
async def callback(interaction: nextcord.Interaction, 멤버: nextcord.Member, 금액: str, 선택: str = SlashOption(
    description="추가 혹은 차감",
    required=True,
    choices=["추가", "차감"])):
    if on_run:
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return
        
        try:
            userid = 멤버.id
            select_user = await bot.fetch_user(userid)
        except Exception as e:
            await interaction.response.send_message(f"사용자 id를 확인해주세요", ephemeral=True)
            return
        
        if select_user:
            user_data = get_user_data(interaction.guild.id, select_user.id)
            
            try:
                amount = validate_positive_int(금액, MAX_PRICE)
            except ValueError as e:
                await interaction.response.send_message(f"올바른 금액을 입력해주세요: {str(e)}", ephemeral=True)
                return
            
            if 선택 == "추가":
                try:
                    user_data['balance'] = safe_add(user_data['balance'], amount)
                    update_user_data(interaction.guild.id, select_user.id, user_data)
                    
                    embed = nextcord.Embed(title="💰ㆍ잔액 추가 완료", color=0x00ff00)
                    embed.add_field(name="대상 사용자", value=f"**{select_user.name}**", inline=True)
                    embed.add_field(name="추가 금액", value=f"**{amount:,}원**", inline=True)
                    embed.add_field(name="현재 잔액", value=f"**{user_data['balance']:,}원**", inline=True)
                    embed.set_thumbnail(url=select_user.display_avatar.url)
                    embed.set_footer(text=f"관리자: {interaction.user.name} | ID: {select_user.id}")
                    embed.timestamp = datetime.datetime.now()
                    
                    await interaction.response.send_message(embed=embed)
                except ValueError as e:
                    await interaction.response.send_message(f"잔액 추가 중 오류가 발생했습니다: {str(e)}", ephemeral=True)
            elif 선택 == "차감":
                try:
                    if user_data['balance'] < amount:
                        embed = nextcord.Embed(title="❌ㆍ잔액 부족", color=0xff0000)
                        embed.add_field(name="대상 사용자", value=f"**{select_user.name}**", inline=True)
                        embed.add_field(name="차감 시도 금액", value=f"**{amount:,}원**", inline=True)
                        embed.add_field(name="현재 잔액", value=f"**{user_data['balance']:,}원**", inline=True)
                        embed.set_thumbnail(url=select_user.display_avatar.url)
                        embed.set_footer(text=f"관리자: {interaction.user.name} | ID: {select_user.id}")
                        embed.timestamp = datetime.datetime.now()
                        
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return
                    
                    user_data['balance'] = safe_add(user_data['balance'], -amount)
                    update_user_data(interaction.guild.id, select_user.id, user_data)
                    
                    embed = nextcord.Embed(title="💰ㆍ잔액 차감 완료", color=0xff6b6b)
                    embed.add_field(name="대상 사용자", value=f"**{select_user.name}**", inline=True)
                    embed.add_field(name="차감 금액", value=f"**{amount:,}원**", inline=True)
                    embed.add_field(name="현재 잔액", value=f"**{user_data['balance']:,}원**", inline=True)
                    embed.set_thumbnail(url=select_user.display_avatar.url)
                    embed.set_footer(text=f"관리자: {interaction.user.name} | ID: {select_user.id}")
                    embed.timestamp = datetime.datetime.now()
                    
                    await interaction.response.send_message(embed=embed)
                except ValueError as e:
                    await interaction.response.send_message(f"잔액 차감 중 오류가 발생했습니다: {str(e)}", ephemeral=True)
@bot.slash_command(name="내정보", description=f"{SERVICE_NAME} | 내 정보를 확인합니다.")
async def callback(interaction: nextcord.Interaction, 사용자: nextcord.Member = None):
    if on_run:
        if interaction.guild is None:
            await interaction.response.send_message("이 명령어는 서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        
        target_user = 사용자 if 사용자 else interaction.user
        
        if 사용자 and interaction.user.id not in admin_ids:
            await interaction.response.send_message("다른 사용자의 정보는 관리자만 조회할 수 있습니다.", ephemeral=True)
            return
        
        user_data = get_user_data(interaction.guild.id, target_user.id)
        
        level_colors = {
            "유저": 0x808080,
            "구매자": 0x00ff00,
            "리셀러": 0x1abc9c
        }
        
        if is_reseller(target_user, interaction.guild):
            display_level = "리셀러"
        elif user_data['total_spent'] == 0:
            display_level = "유저"
        else:
            display_level = "구매자"
        
        color = level_colors.get(display_level, 0x808080)
        
        level_emojis = {
            "유저": "👤",
            "구매자": "🛒",
            "리셀러": "💎"
        }
        
        level_descriptions = {
            "유저": "아직 구매 이력이 없습니다",
            "구매자": "구매자 역할이 지급됩니다",
            "리셀러": "충전 시 20% 추가 충전 혜택"
        }
        
        embed = nextcord.Embed(
            title=f"{level_emojis.get(display_level, '👤')} 사용자 정보",
            description=f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n**{target_user.name}**님의 정보입니다\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            color=color
        )
        
        embed.add_field(
            name="💰 잔액",
            value=f"```\n{user_data['balance']:,}원\n```",
            inline=True
        )
        
        embed.add_field(
            name="📊 등급",
            value=f"```\n{display_level} {level_emojis.get(display_level, '👤')}\n```",
            inline=True
        )
        
        embed.add_field(
            name="💳 총 구매액",
            value=f"```\n{user_data['total_spent']:,}원\n```",
            inline=True
        )
        
        benefit_emoji = "🎁" if display_level == "리셀러" else "✨" if display_level == "구매자" else "📌"
        embed.add_field(
            name=f"{benefit_emoji} 등급 혜택",
            value=f"```\n{level_descriptions.get(display_level, '할인 없음')}\n```",
            inline=False
        )
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.set_footer(text=f"ID: {target_user.id} • {interaction.guild.name}", icon_url=target_user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.slash_command(name="쿠폰생성", description=f"{SERVICE_NAME} | 쿠폰을 생성합니다. (관리자 전용)")
async def create_coupon_command(interaction: nextcord.Interaction, 갯수: int, 금액: int):
    if on_run:
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return
        
        if 갯수 <= 0 or 갯수 > 100:
            await interaction.response.send_message("갯수는 1개 이상 100개 이하여야 합니다.", ephemeral=True)
            return
        
        if 금액 <= 0 or 금액 > MAX_PRICE:
            await interaction.response.send_message(f"금액은 1원 이상 {MAX_PRICE:,}원 이하여야 합니다.", ephemeral=True)
            return
        
        try:
            global COUPONS
            created_coupons = []
            
            for _ in range(갯수):
                coupon_code = generate_coupon_code()
                while coupon_code in COUPONS:
                    coupon_code = generate_coupon_code()
                
                COUPONS[coupon_code] = {
                    "amount": 금액,
                    "used": False,
                    "used_by": None,
                    "created_at": datetime.datetime.now().isoformat()
                }
                created_coupons.append(coupon_code)
            
            save_coupons(COUPONS)
            
            coupons_text = "\n".join(created_coupons[:50])
            if len(created_coupons) > 50:
                coupons_text += f"\n... 외 {len(created_coupons) - 50}개"
            
            embed = nextcord.Embed(title="✅ 쿠폰 생성 완료", color=0x00ff00)
            embed.add_field(name="생성 갯수", value=f"{갯수}개", inline=True)
            embed.add_field(name="쿠폰 금액", value=f"{금액:,}원", inline=True)
            embed.add_field(name="쿠폰 코드", value=f"```\n{coupons_text}\n```", inline=False)
            embed.set_footer(text=f"관리자: {interaction.user.name}")
            embed.timestamp = datetime.datetime.now()
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"쿠폰 생성 중 오류가 발생했습니다: {e}", ephemeral=True)

class StockEditModal(nextcord.ui.Modal):
    def __init__(self, 작업, 타입, 이름, 카테고리, 기존가격=0):
        super().__init__(
            title=f"재고수정 - {작업}",
            custom_id="stock_edit_modal",
            timeout=None
        )
        self.작업 = 작업
        self.타입 = 타입
        self.이름 = 이름
        self.카테고리 = 카테고리
        self.기존가격 = 기존가격
        
        self.product_name_field = nextcord.ui.TextInput(
            label="제품명 (기존)",
            placeholder=f"제품명: {이름}",
            required=False,
            style=nextcord.TextInputStyle.short,
            custom_id="product_name"
        )
        self.add_item(self.product_name_field)
        
        self.category_field = nextcord.ui.TextInput(
            label="카테고리 (기존)",
            placeholder=f"카테고리: {카테고리 if 카테고리 else '없음'}",
            required=False,
            style=nextcord.TextInputStyle.short,
            custom_id="category"
        )
        self.add_item(self.category_field)
        
        self.price_field = nextcord.ui.TextInput(
            label="가격 (수정)",
            placeholder=f"현재 가격: {기존가격:,}원" if 기존가격 > 0 else "가격을 입력하세요",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="price"
        )
        self.add_item(self.price_field)
    
    async def callback(self, interaction: nextcord.Interaction) -> None:
        if interaction.response.is_done():
            return
        
        try:
            price_str = self.price_field.value.strip()
            if not price_str:
                await interaction.response.send_message("가격을 입력해주세요.", ephemeral=True)
                return
            
            try:
                new_price = int(price_str)
                if new_price <= 0:
                    await interaction.response.send_message("가격은 0보다 커야 합니다.", ephemeral=True)
                    return
            except ValueError:
                await interaction.response.send_message("올바른 가격을 입력해주세요.", ephemeral=True)
                return
            
            stock_base_dir = 'stock'
            os.makedirs(stock_base_dir, exist_ok=True)
            
            if self.작업 == "추가":
                category_path = os.path.join(stock_base_dir, self.카테고리)
                if not os.path.exists(category_path):
                    os.makedirs(category_path, exist_ok=True)
                
                timestamp = int(datetime.datetime.now().timestamp() * 1000)
                filename = f"{self.이름}_{new_price}_{timestamp}.txt"
                file_path = os.path.join(category_path, filename)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("")
                
                embed = nextcord.Embed(title="✅ㆍ제품 추가 완료", color=0x00ff00)
                embed.add_field(name="제품명", value=self.이름, inline=True)
                embed.add_field(name="카테고리", value=self.카테고리, inline=True)
                embed.add_field(name="가격", value=f"{new_price:,}원", inline=True)
                if self.기존가격 > 0:
                    embed.add_field(name="기존 가격", value=f"{self.기존가격:,}원", inline=True)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            elif self.작업 == "가격수정":
                category_path = os.path.join(stock_base_dir, self.카테고리)
                if not os.path.exists(category_path):
                    await interaction.response.send_message(f"존재하지 않는 카테고리입니다: {self.카테고리}", ephemeral=True)
                    return
                
                updated_count = 0
                for filename in os.listdir(category_path):
                    if filename.endswith('.txt'):
                        parsed = parse_filename(filename)
                        if not parsed or 'product_name' not in parsed:
                            continue
                        file_product_name = parsed['product_name']
                        if file_product_name == self.이름:
                            old_file_path = os.path.join(category_path, filename)
                            try:
                                with open(old_file_path, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                
                                timestamp = parsed.get('timestamp')
                                if timestamp is None:
                                    timestamp = str(int(datetime.datetime.now().timestamp() * 1000))
                                else:
                                    timestamp = str(timestamp)
                                
                                new_filename = f"{self.이름}_{new_price}_{timestamp}.txt"
                                new_file_path = os.path.join(category_path, new_filename)
                                
                                with open(new_file_path, 'w', encoding='utf-8') as f:
                                    f.write(content)
                                
                                os.remove(old_file_path)
                                updated_count += 1
                            except Exception as e:
                                print(f"가격 수정 오류: {filename} - {e}")
                
                if updated_count == 0:
                    await interaction.response.send_message(f"제품을 찾을 수 없습니다: {self.이름}", ephemeral=True)
                    return
                
                embed = nextcord.Embed(title="✅ㆍ가격 수정 완료", color=0xffd700)
                embed.add_field(name="제품명", value=self.이름, inline=True)
                embed.add_field(name="카테고리", value=self.카테고리, inline=True)
                embed.add_field(name="기존 가격", value=f"{self.기존가격:,}원", inline=True)
                embed.add_field(name="새 가격", value=f"{new_price:,}원", inline=True)
                embed.add_field(name="수정된 파일 수", value=f"{updated_count}개", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            await interaction.response.send_message(f"작업 중 오류가 발생했습니다: {str(e)}", ephemeral=True)
class CategoryAddModal(nextcord.ui.Modal):
    def __init__(self):
        super().__init__(title="카테고리 추가", custom_id="category_add_modal", timeout=None)
        self.name_field = nextcord.ui.TextInput(
            label="카테고리명",
            placeholder="예: 발로란트",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="category_name"
        )
        self.add_item(self.name_field)
        
        self.emoji_field = nextcord.ui.TextInput(
            label="이모지 (선택사항)",
            placeholder="예: 🎮 또는 <:emoji_name:1234567890>",
            required=False,
            style=nextcord.TextInputStyle.short,
            custom_id="category_emoji"
        )
        self.add_item(self.emoji_field)
    
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.response.is_done():
            return
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        category_name = self.name_field.value.strip()
        if not category_name:
            await interaction.response.send_message("카테고리명을 입력해주세요.", ephemeral=True)
            return
        
        emoji = self.emoji_field.value.strip() if self.emoji_field.value else ""
        
        stock_base_dir = 'stock'
        category_path = os.path.join(stock_base_dir, category_name)
        if os.path.exists(category_path):
            await interaction.response.send_message(f"이미 존재하는 카테고리입니다: {category_name}", ephemeral=True)
            return
        
        os.makedirs(category_path, exist_ok=True)
        
        if emoji:
            emoji_data = load_json_data('category_emojis')
            if not emoji_data:
                emoji_data = {}
            emoji_data[category_name] = emoji
            save_json_data('category_emojis', emoji_data)
        
        embed = nextcord.Embed(title="✅ㆍ카테고리 추가 완료", color=0x00ff00)
        display_name = f"{emoji} {category_name}" if emoji else category_name
        embed.add_field(name="카테고리명", value=display_name, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
class ProductAddModal(nextcord.ui.Modal):
    def __init__(self):
        super().__init__(title="제품 추가", custom_id="product_add_modal", timeout=None)
        self.name_field = nextcord.ui.TextInput(
            label="제품명",
            placeholder="예: ",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="product_name"
        )
        self.add_item(self.name_field)
        
        self.emoji_field = nextcord.ui.TextInput(
            label="이모지 (선택사항)",
            placeholder="예: 🎮 또는 <:emoji_name:1234567890>",
            required=False,
            style=nextcord.TextInputStyle.short,
            custom_id="product_emoji"
        )
        self.add_item(self.emoji_field)
        
        self.category_field = nextcord.ui.TextInput(
            label="카테고리명",
            placeholder="예: 발로란트",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="category"
        )
        self.add_item(self.category_field)
        
        self.price_field = nextcord.ui.TextInput(
            label="가격",
            placeholder="예: 10000",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="price"
        )
        self.add_item(self.price_field)
    
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.response.is_done():
            return
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        product_name = self.name_field.value.strip()
        emoji = self.emoji_field.value.strip() if self.emoji_field.value else ""
        category_name = self.category_field.value.strip()
        price_str = self.price_field.value.strip()
        
        if not product_name or not category_name or not price_str:
            await interaction.response.send_message("제품명, 카테고리명, 가격을 입력해주세요.", ephemeral=True)
            return
        
        try:
            price = int(price_str)
            if price <= 0:
                await interaction.response.send_message("가격은 0보다 커야 합니다.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("올바른 가격을 입력해주세요.", ephemeral=True)
            return
        
        stock_base_dir = 'stock'
        category_path = os.path.join(stock_base_dir, category_name)
        if not os.path.exists(category_path):
            os.makedirs(category_path, exist_ok=True)
        
        if emoji:
            emoji_data = load_json_data('product_emojis')
            if not emoji_data:
                emoji_data = {}
            if category_name not in emoji_data:
                emoji_data[category_name] = {}
            emoji_data[category_name][product_name] = emoji
            save_json_data('product_emojis', emoji_data)
        
        existing_info = get_product_info_from_stock(product_name, category_name)
        timestamp = int(datetime.datetime.now().timestamp() * 1000)
        filename = f"{product_name}_{price}_{timestamp}.txt"
        file_path = os.path.join(category_path, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("")
        
        embed = nextcord.Embed(title="✅ㆍ제품 추가 완료", color=0x00ff00)
        embed.add_field(name="제품명", value=product_name, inline=True)
        embed.add_field(name="카테고리", value=category_name, inline=True)
        embed.add_field(name="가격", value=f"{price:,}원", inline=True)
        if existing_info:
            embed.add_field(name="기존 정보", value=f"기존 가격: {existing_info.get('price', 0):,}원", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
class CategoryRemoveSelect(nextcord.ui.Select):
    def __init__(self):
        categories = get_categories_from_stock_folder()
        options = []
        
        if categories:
            for category in categories[:25]:
                options.append(nextcord.SelectOption(label=category, description=f"{category} 카테고리", value=category))
        else:
            options.append(nextcord.SelectOption(label='카테고리가 없습니다', description='카테고리를 먼저 추가해주세요', value='none', disabled=True))
        
        if not options:
            options = [nextcord.SelectOption(label='카테고리가 없습니다', description='카테고리를 먼저 추가해주세요', value='none', disabled=True)]
        
        super().__init__(custom_id='category_remove_select', placeholder="제거할 카테고리를 선택하세요", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        category_name = self.values[0]
        if category_name == 'none':
            await interaction.response.send_message("카테고리를 먼저 추가해주세요.", ephemeral=True)
            return
        
        stock_base_dir = 'stock'
        category_path = os.path.join(stock_base_dir, category_name)
        if not os.path.exists(category_path):
            await interaction.response.send_message(f"존재하지 않는 카테고리입니다: {category_name}", ephemeral=True)
            return
        
        files = [f for f in os.listdir(category_path) if f.endswith('.txt')]
        if files:
            await interaction.response.send_message(f"카테고리 내에 제품이 있어 삭제할 수 없습니다. 먼저 제품을 제거해주세요.", ephemeral=True)
            return
        
        os.rmdir(category_path)
        embed = nextcord.Embed(title="✅ㆍ카테고리 제거 완료", color=0xff6b6b)
        embed.add_field(name="카테고리명", value=category_name, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
class CategoryRemoveSelectView(nextcord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CategoryRemoveSelect())
class ProductRemoveModal(nextcord.ui.Modal):
    def __init__(self):
        super().__init__(title="제품 제거", custom_id="product_remove_modal", timeout=None)
        self.name_field = nextcord.ui.TextInput(
            label="제품명",
            placeholder="예: ",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="product_name"
        )
        self.add_item(self.name_field)
        
        self.category_field = nextcord.ui.TextInput(
            label="카테고리명",
            placeholder="예: 발로란트",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="category"
        )
        self.add_item(self.category_field)
    
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.response.is_done():
            return
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        product_name = self.name_field.value.strip()
        category_name = self.category_field.value.strip()
        
        if not product_name or not category_name:
            await interaction.response.send_message("모든 항목을 입력해주세요.", ephemeral=True)
            return
        
        stock_base_dir = 'stock'
        category_path = os.path.join(stock_base_dir, category_name)
        if not os.path.exists(category_path):
            await interaction.response.send_message(f"존재하지 않는 카테고리입니다: {category_name}", ephemeral=True)
            return
        
        removed_count = 0
        for filename in os.listdir(category_path):
            if filename.endswith('.txt'):
                parsed = parse_filename(filename)
                if not parsed or 'product_name' not in parsed:
                    continue
                file_product_name = parsed['product_name']
                if file_product_name == product_name:
                        file_path = os.path.join(category_path, filename)
                        try:
                            os.remove(file_path)
                            removed_count += 1
                        except Exception as e:
                            print(f"파일 삭제 오류: {filename} - {e}")
        
        if removed_count == 0:
            await interaction.response.send_message(f"제품을 찾을 수 없습니다: {product_name}", ephemeral=True)
            return
        
        embed = nextcord.Embed(title="✅ㆍ제품 제거 완료", color=0xff6b6b)
        embed.add_field(name="제품명", value=product_name, inline=True)
        embed.add_field(name="카테고리", value=category_name, inline=True)
        embed.add_field(name="삭제된 파일 수", value=f"{removed_count}개", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
class PriceEditModal(nextcord.ui.Modal):
    def __init__(self):
        super().__init__(title="가격수정", custom_id="price_edit_modal", timeout=None)
        self.name_field = nextcord.ui.TextInput(
            label="제품명",
            placeholder="예: ",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="product_name"
        )
        self.add_item(self.name_field)
        
        self.category_field = nextcord.ui.TextInput(
            label="카테고리명",
            placeholder="예: 발로란트",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="category"
        )
        self.add_item(self.category_field)
        
        self.price_field = nextcord.ui.TextInput(
            label="새 가격",
            placeholder="예: 15000",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="new_price"
        )
        self.add_item(self.price_field)
    
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.response.is_done():
            return
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        product_name = self.name_field.value.strip()
        category_name = self.category_field.value.strip()
        price_str = self.price_field.value.strip()
        
        if not product_name or not category_name or not price_str:
            await interaction.response.send_message("모든 항목을 입력해주세요.", ephemeral=True)
            return
        
        try:
            new_price = int(price_str)
            if new_price <= 0:
                await interaction.response.send_message("가격은 0보다 커야 합니다.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("올바른 가격을 입력해주세요.", ephemeral=True)
            return
        
        existing_info = get_product_info_from_stock(product_name, category_name)
        if not existing_info:
            await interaction.response.send_message(f"제품을 찾을 수 없습니다: {product_name}", ephemeral=True)
            return
        
        stock_base_dir = 'stock'
        category_path = os.path.join(stock_base_dir, category_name)
        if not os.path.exists(category_path):
            await interaction.response.send_message(f"존재하지 않는 카테고리입니다: {category_name}", ephemeral=True)
            return
        
        updated_count = 0
        for filename in os.listdir(category_path):
            if filename.endswith('.txt'):
                parsed = parse_filename(filename)
                if not parsed or 'product_name' not in parsed:
                    continue
                file_product_name = parsed['product_name']
                if file_product_name == product_name:
                        old_file_path = os.path.join(category_path, filename)
                        try:
                            with open(old_file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            timestamp = parsed.get('timestamp')
                            if timestamp is None:
                                timestamp = str(int(datetime.datetime.now().timestamp() * 1000))
                            else:
                                timestamp = str(timestamp)
                            
                            new_filename = f"{product_name}_{new_price}_{timestamp}.txt"
                            new_file_path = os.path.join(category_path, new_filename)
                            
                            with open(new_file_path, 'w', encoding='utf-8') as f:
                                f.write(content)
                            
                            os.remove(old_file_path)
                            updated_count += 1
                        except Exception as e:
                            print(f"가격 수정 오류: {filename} - {e}")
        
        if updated_count == 0:
            await interaction.response.send_message(f"제품을 찾을 수 없습니다: {product_name}", ephemeral=True)
            return
        
        embed = nextcord.Embed(title="✅ㆍ가격 수정 완료", color=0xffd700)
        embed.add_field(name="제품명", value=product_name, inline=True)
        embed.add_field(name="카테고리", value=category_name, inline=True)
        embed.add_field(name="기존 가격", value=f"{existing_info.get('price', 0):,}원", inline=True)
        embed.add_field(name="새 가격", value=f"{new_price:,}원", inline=True)
        embed.add_field(name="수정된 파일 수", value=f"{updated_count}개", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
class StockCategorySelect(nextcord.ui.Select):
    def __init__(self, action_type):
        self.action_type = action_type
        categories = get_categories_from_stock_folder()
        options = []
        
        if categories:
            for category in categories[:25]:
                options.append(nextcord.SelectOption(label=category, description=f"{category} 카테고리", value=category))
        else:
            options.append(nextcord.SelectOption(label='카테고리가 없습니다', description='카테고리를 먼저 추가해주세요', value='none', disabled=True))
        
        if not options:
            options = [nextcord.SelectOption(label='카테고리가 없습니다', description='카테고리를 먼저 추가해주세요', value='none', disabled=True)]
        
        placeholder = {
            "add": "제품을 추가할 카테고리를 선택하세요",
            "remove": "제품을 제거할 카테고리를 선택하세요",
            "price_edit": "가격을 수정할 제품의 카테고리를 선택하세요",
            "stock_edit": "재고를 수정할 제품의 카테고리를 선택하세요",
            "order_edit": "순서를 수정할 제품의 카테고리를 선택하세요"
        }.get(action_type, "카테고리를 선택하세요")
        
        super().__init__(custom_id=f'stock_category_select_{action_type}', placeholder=placeholder, min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        category = self.values[0]
        if category == 'none':
            await interaction.response.send_message("카테고리를 먼저 추가해주세요.", ephemeral=True)
            return
        
        if self.action_type == "add":
            embed = nextcord.Embed(title="📦 제품 추가", color=0x00ff00)
            embed.add_field(name="카테고리", value=category, inline=False)
            embed.add_field(name="", value="제품명과 가격을 입력하세요.", inline=False)
            await interaction.response.send_message(embed=embed, view=StockProductAddView(category), ephemeral=True)
        elif self.action_type == "remove":
            products = get_products_from_category(category)
            if not products:
                await interaction.response.send_message(f"{category} 카테고리에 제품이 없습니다.", ephemeral=True)
                return
            embed = nextcord.Embed(title="🗑️ 제품 제거", color=0xff6b6b)
            embed.add_field(name="카테고리", value=category, inline=False)
            embed.add_field(name="", value="제거할 제품을 선택하세요.", inline=False)
            await interaction.response.send_message(embed=embed, view=StockProductSelectView(category, "remove"), ephemeral=True)
        elif self.action_type == "price_edit":
            products = get_products_from_category(category)
            if not products:
                await interaction.response.send_message(f"{category} 카테고리에 제품이 없습니다.", ephemeral=True)
                return
            embed = nextcord.Embed(title="💰 가격수정", color=0xffd700)
            embed.add_field(name="카테고리", value=category, inline=False)
            embed.add_field(name="", value="가격을 수정할 제품을 선택하세요.", inline=False)
            await interaction.response.send_message(embed=embed, view=StockProductSelectView(category, "price_edit"), ephemeral=True)
        elif self.action_type == "stock_edit":
            products = get_products_from_category(category)
            if not products:
                await interaction.response.send_message(f"{category} 카테고리에 제품이 없습니다.", ephemeral=True)
                return
            embed = nextcord.Embed(title="📦 재고수정", color=0x3498db)
            embed.add_field(name="카테고리", value=category, inline=False)
            embed.add_field(name="", value="재고를 수정할 제품을 선택하세요.", inline=False)
            await interaction.response.send_message(embed=embed, view=StockProductSelectView(category, "stock_edit"), ephemeral=True)
        elif self.action_type == "order_edit":
            products = get_products_from_category(category)
            if not products:
                await interaction.response.send_message(f"{category} 카테고리에 제품이 없습니다.", ephemeral=True)
                return
            await interaction.response.send_message(embed=ProductOrderEditView.create_embed(category, products), view=ProductOrderEditView(category, products), ephemeral=True)
class StockCategorySelectView(nextcord.ui.View):
    def __init__(self, action_type):
        super().__init__(timeout=None)
        self.add_item(StockCategorySelect(action_type))
class StockProductSelect(nextcord.ui.Select):
    def __init__(self, category, action_type):
        self.category = category
        self.action_type = action_type
        products = get_products_from_category(category)
        options = []
        
        for product_name, product_data in list(products.items())[:25]:
            product_emoji = get_product_emoji(category, product_name)
            label = f"{product_emoji} {product_data['name']}" if product_emoji else product_data['name']
            description = f"{product_data['price']:,}원 | 재고 {product_data['stock']:,}개"
            value = product_name
            options.append(nextcord.SelectOption(label=label, description=description, value=value))
        
        if not options:
            options = [nextcord.SelectOption(label='제품이 없습니다', description='제품이 없습니다', value='none', disabled=True)]
        
        placeholder = {
            "remove": "제거할 제품을 선택하세요",
            "price_edit": "가격을 수정할 제품을 선택하세요",
            "stock_edit": "재고를 수정할 제품을 선택하세요",
            "order_edit": "순서를 수정할 제품의 카테고리를 선택하세요"
        }.get(action_type, "제품을 선택하세요")
        
        super().__init__(custom_id=f'stock_product_select_{action_type}', placeholder=placeholder, min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        product_name = self.values[0]
        if product_name == 'none':
            await interaction.response.send_message("제품을 찾을 수 없습니다.", ephemeral=True)
            return
        
        if self.action_type == "remove":
            stock_base_dir = 'stock'
            category_path = os.path.join(stock_base_dir, self.category)
            if not os.path.exists(category_path):
                await interaction.response.send_message(f"존재하지 않는 카테고리입니다: {self.category}", ephemeral=True)
                return
            
            removed_count = 0
            for filename in os.listdir(category_path):
                if filename.endswith('.txt'):
                    name_part = filename.replace('.txt', '')
                    if '_' in name_part:
                        file_product_name = name_part.split('_')[0]
                        if file_product_name == product_name:
                            file_path = os.path.join(category_path, filename)
                            try:
                                os.remove(file_path)
                                removed_count += 1
                            except Exception as e:
                                print(f"파일 삭제 오류: {filename} - {e}")
            
            if removed_count == 0:
                await interaction.response.send_message(f"제품을 찾을 수 없습니다: {product_name}", ephemeral=True)
                return
            
            embed = nextcord.Embed(title="✅ㆍ제품 제거 완료", color=0xff6b6b)
            embed.add_field(name="제품명", value=product_name, inline=True)
            embed.add_field(name="카테고리", value=self.category, inline=True)
            embed.add_field(name="삭제된 파일 수", value=f"{removed_count}개", inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif self.action_type == "price_edit":
            existing_info = get_product_info_from_stock(product_name, self.category)
            if not existing_info:
                await interaction.response.send_message(f"제품을 찾을 수 없습니다: {product_name}", ephemeral=True)
                return
            
            await interaction.response.send_modal(StockPriceEditModal(product_name, self.category, existing_info.get('price', 0)))
        elif self.action_type == "stock_edit":
            existing_info = get_product_info_from_stock(product_name, self.category)
            if not existing_info:
                await interaction.response.send_message(f"제품을 찾을 수 없습니다: {product_name}", ephemeral=True)
                return
            
            current_stock = existing_info.get('stock', 0)
            
            existing_stock_lines = []
            stock_base_dir = 'stock'
            category_path = os.path.join(stock_base_dir, self.category)
            if os.path.exists(category_path):
                for filename in os.listdir(category_path):
                    if filename.endswith('.txt'):
                        parsed = parse_filename(filename)
                        if not parsed or 'product_name' not in parsed:
                            continue
                        file_product_name = parsed['product_name']
                        if file_product_name == product_name:
                            file_path = os.path.join(category_path, filename)
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    lines = f.readlines()
                                    existing_stock_lines = [line.strip() for line in lines if line.strip()]
                                break
                            except Exception as e:
                                print(f"재고 파일 읽기 오류: {filename} - {e}")
            
            if existing_stock_lines:
                existing_stock_text = "\n".join(existing_stock_lines)
                if len(existing_stock_text) > 4000:
                    embed = nextcord.Embed(
                        title="⚠️ 재고 수정 불가",
                        description=f"기존 재고가 Discord의 최대 입력 길이(4000자)를 초과합니다.\n\n현재 재고 텍스트 길이: {len(existing_stock_text):,}자\n\n재고를 수정하려면 먼저 일부 재고를 삭제하여 4000자 이하로 만든 후 다시 시도해주세요.",
                        color=0xff6b6b
                    )
                    embed.add_field(name="현재 재고 수", value=f"{len(existing_stock_lines):,}개", inline=True)
                    embed.add_field(name="텍스트 길이", value=f"{len(existing_stock_text):,}자", inline=True)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            
            await interaction.response.send_modal(StockQuantityEditModal(product_name, self.category, current_stock, existing_stock_lines))
class StockProductSelectView(nextcord.ui.View):
    def __init__(self, category, action_type):
        super().__init__(timeout=None)
        self.add_item(StockProductSelect(category, action_type))
class StockProductAddView(nextcord.ui.View):
    def __init__(self, category):
        super().__init__(timeout=None)
        self.category = category
    
    @nextcord.ui.button(label="제품 추가하기", style=nextcord.ButtonStyle.secondary, custom_id="stock_product_add_confirm")
    async def add_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(ProductAddModalWithCategory(self.category))
class ProductAddModalWithCategory(nextcord.ui.Modal):
    def __init__(self, category):
        super().__init__(title="제품 추가", custom_id="product_add_modal_category", timeout=None)
        self.category = category
        
        self.name_field = nextcord.ui.TextInput(
            label="제품명",
            placeholder="예: ",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="product_name"
        )
        self.add_item(self.name_field)
        
        self.emoji_field = nextcord.ui.TextInput(
            label="이모지 (선택사항)",
            placeholder="예: 🎮 또는 <:emoji_name:1234567890>",
            required=False,
            style=nextcord.TextInputStyle.short,
            custom_id="product_emoji"
        )
        self.add_item(self.emoji_field)
        
        self.price_field = nextcord.ui.TextInput(
            label="가격",
            placeholder="예: 10000",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="price"
        )
        self.add_item(self.price_field)
    
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.response.is_done():
            return
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        product_name = self.name_field.value.strip()
        emoji = self.emoji_field.value.strip() if self.emoji_field.value else ""
        price_str = self.price_field.value.strip()
        
        if not product_name or not price_str:
            await interaction.response.send_message("제품명과 가격을 입력해주세요.", ephemeral=True)
            return
        
        try:
            price = int(price_str)
            if price <= 0:
                await interaction.response.send_message("가격은 0보다 커야 합니다.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("올바른 가격을 입력해주세요.", ephemeral=True)
            return
        
        stock_base_dir = 'stock'
        category_path = os.path.join(stock_base_dir, self.category)
        if not os.path.exists(category_path):
            os.makedirs(category_path, exist_ok=True)
        
        if emoji:
            emoji_data = load_json_data('product_emojis')
            if not emoji_data:
                emoji_data = {}
            if self.category not in emoji_data:
                emoji_data[self.category] = {}
            emoji_data[self.category][product_name] = emoji
            save_json_data('product_emojis', emoji_data)
        
        existing_info = get_product_info_from_stock(product_name, self.category)
        timestamp = int(datetime.datetime.now().timestamp() * 1000)
        filename = f"{product_name}_{price}_{timestamp}.txt"
        file_path = os.path.join(category_path, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("")
        
        embed = nextcord.Embed(title="✅ㆍ제품 추가 완료", color=0x00ff00)
        display_name = f"{emoji} {product_name}" if emoji else product_name
        embed.add_field(name="제품명", value=display_name, inline=True)
        embed.add_field(name="카테고리", value=self.category, inline=True)
        embed.add_field(name="가격", value=f"{price:,}원", inline=True)
        if existing_info:
            embed.add_field(name="기존 정보", value=f"기존 가격: {existing_info.get('price', 0):,}원", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
class StockQuantityEditModal(nextcord.ui.Modal):
    def __init__(self, product_name, category, current_stock, existing_stock_lines=None):
        super().__init__(title="재고수정", custom_id="stock_quantity_edit_modal", timeout=None)
        self.product_name = product_name
        self.category = category
        self.current_stock = current_stock
        
        existing_stock_text = ""
        if existing_stock_lines:
            existing_stock_text = "\n".join(existing_stock_lines)
            if len(existing_stock_text) > 4000:
                truncated_lines = []
                current_length = 0
                for line in existing_stock_lines:
                    line_with_newline = line + "\n"
                    if current_length + len(line_with_newline) > 3900:
                        truncated_lines.append("... (더 많은 재고가 있습니다)")
                        break
                    truncated_lines.append(line)
                    current_length += len(line_with_newline)
                existing_stock_text = "\n".join(truncated_lines)
        
        placeholder_text = "기존 재고 라인을 수정하거나 삭제할 수 있습니다.\n라인을 삭제하려면 해당 라인을 지우세요."
        if existing_stock_text:
            preview = existing_stock_text[:200] + "..." if len(existing_stock_text) > 200 else existing_stock_text
            placeholder_text = f"기존 재고 (미리보기):\n{preview}"
        
        if len(placeholder_text) > 100:
            placeholder_text = placeholder_text[:97] + "..."
        
        text_input_kwargs = dict(
            label="기존 재고 (수정/삭제 가능)",
            placeholder=placeholder_text,
            required=False,
            style=nextcord.TextInputStyle.paragraph,
            custom_id="existing_stock"
        )
        if existing_stock_text:
            text_input_kwargs["value"] = existing_stock_text
        
        try:
            self.existing_stock_field = nextcord.ui.TextInput(**text_input_kwargs)
        except TypeError:
            text_input_kwargs.pop("value", None)
            self.existing_stock_field = nextcord.ui.TextInput(**text_input_kwargs)
        self.add_item(self.existing_stock_field)
        if existing_stock_text:
            for attr_name in ("value", "default", "_value", "_default"):
                if hasattr(self.existing_stock_field, attr_name):
                    try:
                        setattr(self.existing_stock_field, attr_name, existing_stock_text)
                        break
                    except Exception:
                        continue
            underlying = getattr(self.existing_stock_field, "_underlying", None)
            if underlying is not None and hasattr(underlying, "value"):
                try:
                    underlying.value = existing_stock_text
                except Exception:
                    pass
        
        self.existing_stock_lines = existing_stock_lines or []
        
        self.stock_lines_field = nextcord.ui.TextInput(
            label="추가할 재고 라인",
            placeholder="한 줄에 하나씩 재고 항목을 입력하세요.\n예:\n1762546348879\n1762546348880\n1762546348881",
            required=False,
            style=nextcord.TextInputStyle.paragraph,
            custom_id="stock_lines"
        )
        self.add_item(self.stock_lines_field)
    
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.response.is_done():
            return
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        stock_base_dir = 'stock'
        category_path = os.path.join(stock_base_dir, self.category)
        if not os.path.exists(category_path):
            await interaction.response.send_message(f"존재하지 않는 카테고리입니다: {self.category}", ephemeral=True)
            return
        
        product_files = []
        for filename in os.listdir(category_path):
            if filename.endswith('.txt'):
                parsed = parse_filename(filename)
                if not parsed or 'product_name' not in parsed:
                    continue
                file_product_name = parsed['product_name']
                if file_product_name == self.product_name:
                    product_files.append(filename)
        
        if not product_files:
            await interaction.response.send_message(f"제품을 찾을 수 없습니다: {self.product_name}", ephemeral=True)
            return
        
        target_file = product_files[0]
        file_path = os.path.join(category_path, target_file)
        
        try:
            DISCORD_TEXT_INPUT_MAX_LENGTH = 4000
            
            existing_stock_str = self.existing_stock_field.value.strip() if self.existing_stock_field.value else ""
            
            if existing_stock_str and len(existing_stock_str) > DISCORD_TEXT_INPUT_MAX_LENGTH:
                await interaction.response.send_message(
                    f"⚠️ 기존 재고 필드의 입력값이 Discord의 최대 입력 길이(4000자)를 초과합니다.\n\n"
                    f"현재 입력 길이: {len(existing_stock_str):,}자\n"
                    f"최대 허용 길이: {DISCORD_TEXT_INPUT_MAX_LENGTH:,}자\n\n"
                    f"Discord에서 설정한 값에 따라 수정할 수 없습니다. 재고를 분할하여 입력해주세요.",
                    ephemeral=True
                )
                return
            
            if existing_stock_str:
                existing_stock_lines = [line.strip() for line in existing_stock_str.split('\n') if line.strip()]
            else:
                existing_stock_lines = self.existing_stock_lines
            
            new_stock_lines_str = self.stock_lines_field.value.strip() if self.stock_lines_field.value else ""
            
            if new_stock_lines_str and len(new_stock_lines_str) > DISCORD_TEXT_INPUT_MAX_LENGTH:
                await interaction.response.send_message(
                    f"⚠️ 추가할 재고 필드의 입력값이 Discord의 최대 입력 길이(4000자)를 초과합니다.\n\n"
                    f"현재 입력 길이: {len(new_stock_lines_str):,}자\n"
                    f"최대 허용 길이: {DISCORD_TEXT_INPUT_MAX_LENGTH:,}자\n\n"
                    f"Discord에서 설정한 값에 따라 수정할 수 없습니다. 재고를 분할하여 입력해주세요.",
                    ephemeral=True
                )
                return
            
            new_stock_lines = [line.strip() for line in new_stock_lines_str.split('\n') if line.strip()]
            
            if existing_stock_lines and new_stock_lines:
                combined_text = "\n".join(existing_stock_lines + new_stock_lines)
                if len(combined_text) > DISCORD_TEXT_INPUT_MAX_LENGTH:
                    await interaction.response.send_message(
                        f"⚠️ 기존 재고와 추가할 재고를 합친 길이가 Discord의 최대 입력 길이(4000자)를 초과합니다.\n\n"
                        f"합친 텍스트 길이: {len(combined_text):,}자\n"
                        f"최대 허용 길이: {DISCORD_TEXT_INPUT_MAX_LENGTH:,}자\n\n"
                        f"Discord에서 설정한 값에 따라 수정할 수 없습니다. 재고를 분할하여 입력해주세요.",
                        ephemeral=True
                    )
                    return
            
            total_lines = len(existing_stock_lines) + len(new_stock_lines)
            if total_lines > MAX_QUANTITY:
                await interaction.response.send_message(f"총 재고 수는 최대 {MAX_QUANTITY:,}개까지 가능합니다.", ephemeral=True)
                return
            
            all_stock_lines = existing_stock_lines + new_stock_lines
            
            final_lines = []
            for line in all_stock_lines:
                if len(line) > MAX_STRING_LENGTH:
                    line = line[:MAX_STRING_LENGTH]
                if line:
                    final_lines.append(f"{line}\n")
            
            final_stock_text = "".join(final_lines)
            if len(final_stock_text) > DISCORD_TEXT_INPUT_MAX_LENGTH:
                await interaction.response.send_message(
                    f"⚠️ 최종 재고 텍스트 길이가 Discord의 최대 입력 길이(4000자)를 초과합니다.\n\n"
                    f"최종 텍스트 길이: {len(final_stock_text):,}자\n"
                    f"최대 허용 길이: {DISCORD_TEXT_INPUT_MAX_LENGTH:,}자\n\n"
                    f"Discord에서 설정한 값에 따라 수정할 수 없습니다. 재고를 분할하여 입력해주세요.",
                    ephemeral=True
                )
                return
            
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(final_lines)
            except Exception as e:
                await interaction.response.send_message(f"파일 쓰기 중 오류가 발생했습니다: {str(e)}", ephemeral=True)
                return
            
            old_count = self.current_stock
            new_count = len(final_lines)
            added_count = len(new_stock_lines)
            removed_count = old_count - len(existing_stock_lines) if old_count > len(existing_stock_lines) else 0
            
        except Exception as e:
            await interaction.response.send_message(f"재고 수정 중 오류가 발생했습니다: {str(e)}", ephemeral=True)
            return
        
        updated_stock = get_product_stock_count(None, self.product_name)
        
        embed = nextcord.Embed(title="✅ㆍ재고 수정 완료", color=0x00ff00)
        embed.add_field(name="제품명", value=self.product_name, inline=True)
        embed.add_field(name="카테고리", value=self.category, inline=True)
        if added_count > 0:
            embed.add_field(name="추가된 재고", value=f"{added_count:,}개", inline=True)
        if removed_count > 0:
            embed.add_field(name="삭제된 재고", value=f"{removed_count:,}개", inline=True)
        embed.add_field(name="이전 재고", value=f"{old_count:,}개", inline=True)
        embed.add_field(name="현재 재고", value=f"{updated_stock:,}개", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
class ProductOrderEditView(nextcord.ui.View):
    def __init__(self, category, products):
        super().__init__(timeout=None)
        self.category = category
        self.products = products
    
    @staticmethod
    def create_embed(category, products):
        embed = nextcord.Embed(title="📋 제품 순서 수정", color=0x9b59b6)
        category_emoji = get_category_emoji(category)
        category_display = f"{category_emoji} {category}" if category_emoji else category
        embed.add_field(name="카테고리", value=category_display, inline=False)
        embed.add_field(name="", value="아래 버튼을 눌러 제품명을 원하는 순서대로 한 줄에 하나씩 입력하세요.", inline=False)
        
        product_list_text = ""
        current_order = get_product_order(category)
        if current_order:
            for i, product_name in enumerate(current_order, 1):
                if product_name in products:
                    product_emoji = get_product_emoji(category, product_name)
                    product_display = f"{product_emoji} {product_name}" if product_emoji else product_name
                    product_list_text += f"{i}. {product_display}\n"
        
        for product_name in products:
            if product_name not in current_order:
                product_emoji = get_product_emoji(category, product_name)
                product_display = f"{product_emoji} {product_name}" if product_emoji else product_name
                product_list_text += f"- {product_display}\n"
        
        if product_list_text:
            safe_add_field(embed, "현재 제품 목록", product_list_text[:1024], inline=False)
        
        return embed
    
    @nextcord.ui.button(label="순서 입력", style=nextcord.ButtonStyle.secondary, custom_id="product_order_input")
    async def order_input_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(ProductOrderEditModal(self.category, self.products))
class ProductOrderEditModal(nextcord.ui.Modal):
    def __init__(self, category, products):
        super().__init__(title="제품 순서 수정", custom_id="product_order_edit_modal", timeout=None)
        self.category = category
        self.products = products
        
        current_order = get_product_order(category)
        current_order_text = "\n".join(current_order) if current_order else ""
        
        self.order_field = nextcord.ui.TextInput(
            label="제품 순서 (한 줄에 하나씩)",
            placeholder="제품명을 원하는 순서대로 한 줄에 하나씩 입력하세요.\n예:\n제품1\n제품2\n제품3",
            required=False,
            style=nextcord.TextInputStyle.paragraph,
            custom_id="product_order"
        )
        if current_order_text:
            preview = current_order_text[:200] + "..." if len(current_order_text) > 200 else current_order_text
            self.order_field.placeholder = f"현재 순서:\n{preview}\n\n위 형식으로 입력하세요."
        self.add_item(self.order_field)
    
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.response.is_done():
            return
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        order_text = self.order_field.value.strip() if self.order_field.value else ""
        
        if not order_text:
            set_product_order(self.category, [])
            embed = nextcord.Embed(title="✅ㆍ순서 초기화 완료", color=0x9b59b6)
            embed.add_field(name="카테고리", value=self.category, inline=True)
            embed.add_field(name="", value="제품 순서가 초기화되었습니다. 기본 순서로 표시됩니다.", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        order_lines = [line.strip() for line in order_text.split('\n') if line.strip()]
        
        valid_order = []
        invalid_products = []
        
        for product_name in order_lines:
            if product_name in self.products:
                if product_name not in valid_order:
                    valid_order.append(product_name)
            else:
                invalid_products.append(product_name)
        
        set_product_order(self.category, valid_order)
        
        embed = nextcord.Embed(title="✅ㆍ순서 수정 완료", color=0x9b59b6)
        category_emoji = get_category_emoji(self.category)
        category_display = f"{category_emoji} {self.category}" if category_emoji else self.category
        embed.add_field(name="카테고리", value=category_display, inline=True)
        embed.add_field(name="순서가 지정된 제품", value=f"{len(valid_order)}개", inline=True)
        
        if invalid_products:
            invalid_text = ", ".join(invalid_products[:10])
            if len(invalid_products) > 10:
                invalid_text += f" 외 {len(invalid_products) - 10}개"
            safe_add_field(embed, "무시된 제품명", invalid_text, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
class StockPriceEditModal(nextcord.ui.Modal):
    def __init__(self, product_name, category, existing_price):
        super().__init__(title="가격수정", custom_id="stock_price_edit_modal", timeout=None)
        self.product_name = product_name
        self.category = category
        self.existing_price = existing_price
        
        self.name_field = nextcord.ui.TextInput(
            label="제품명 (기존)",
            placeholder=f"제품명: {product_name}",
            required=False,
            style=nextcord.TextInputStyle.short,
            custom_id="product_name_display"
        )
        self.add_item(self.name_field)
        
        self.category_field = nextcord.ui.TextInput(
            label="카테고리 (기존)",
            placeholder=f"카테고리: {category}",
            required=False,
            style=nextcord.TextInputStyle.short,
            custom_id="category_display"
        )
        self.add_item(self.category_field)
        
        existing_emoji = get_product_emoji(category, product_name)
        self.emoji_field = nextcord.ui.TextInput(
            label="이모지 (선택사항)",
            placeholder=f"예: 🎮 또는 <:emoji_name:1234567890> (현재: {existing_emoji if existing_emoji else '없음'})",
            required=False,
            style=nextcord.TextInputStyle.short,
            custom_id="product_emoji"
        )
        self.add_item(self.emoji_field)
        
        self.price_field = nextcord.ui.TextInput(
            label="새 가격",
            placeholder=f"현재 가격: {existing_price:,}원 (새 가격을 입력하세요)",
            required=True,
            style=nextcord.TextInputStyle.short,
            custom_id="new_price"
        )
        self.add_item(self.price_field)
    
    async def callback(self, interaction: nextcord.Interaction):
        if interaction.response.is_done():
            return
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        
        emoji = self.emoji_field.value.strip() if self.emoji_field.value else ""
        if emoji:
            emoji_data = load_json_data('product_emojis')
            if not emoji_data:
                emoji_data = {}
            if self.category not in emoji_data:
                emoji_data[self.category] = {}
            emoji_data[self.category][self.product_name] = emoji
            save_json_data('product_emojis', emoji_data)
        elif emoji == "" and self.emoji_field.value is not None:
            emoji_data = load_json_data('product_emojis')
            if emoji_data and self.category in emoji_data and self.product_name in emoji_data[self.category]:
                del emoji_data[self.category][self.product_name]
                if not emoji_data[self.category]:
                    del emoji_data[self.category]
                save_json_data('product_emojis', emoji_data)
        
        price_str = self.price_field.value.strip()
        if not price_str:
            await interaction.response.send_message("가격을 입력해주세요.", ephemeral=True)
            return
        
        try:
            new_price = int(price_str)
            if new_price <= 0:
                await interaction.response.send_message("가격은 0보다 커야 합니다.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("올바른 가격을 입력해주세요.", ephemeral=True)
            return
        
        stock_base_dir = 'stock'
        category_path = os.path.join(stock_base_dir, self.category)
        if not os.path.exists(category_path):
            await interaction.response.send_message(f"존재하지 않는 카테고리입니다: {self.category}", ephemeral=True)
            return
        
        updated_count = 0
        for filename in os.listdir(category_path):
            if filename.endswith('.txt'):
                name_part = filename.replace('.txt', '')
                if '_' in name_part:
                    file_product_name = name_part.split('_')[0]
                    if file_product_name == self.product_name:
                        old_file_path = os.path.join(category_path, filename)
                        try:
                            parsed = parse_filename(filename)
                            with open(old_file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            timestamp = parsed.get('timestamp')
                            if timestamp is None:
                                timestamp = str(int(datetime.datetime.now().timestamp() * 1000))
                            else:
                                timestamp = str(timestamp)
                            
                            new_filename = f"{self.product_name}_{new_price}_{timestamp}.txt"
                            new_file_path = os.path.join(category_path, new_filename)
                            
                            with open(new_file_path, 'w', encoding='utf-8') as f:
                                f.write(content)
                            
                            os.remove(old_file_path)
                            updated_count += 1
                        except Exception as e:
                            print(f"가격 수정 오류: {filename} - {e}")
        
        if updated_count == 0:
            await interaction.response.send_message(f"제품을 찾을 수 없습니다: {self.product_name}", ephemeral=True)
            return
        
        embed = nextcord.Embed(title="✅ㆍ가격 수정 완료", color=0xffd700)
        product_emoji = get_product_emoji(self.category, self.product_name)
        display_name = f"{product_emoji} {self.product_name}" if product_emoji else self.product_name
        embed.add_field(name="제품명", value=display_name, inline=True)
        category_emoji = get_category_emoji(self.category)
        category_display = f"{category_emoji} {self.category}" if category_emoji else self.category
        embed.add_field(name="카테고리", value=category_display, inline=True)
        embed.add_field(name="기존 가격", value=f"{self.existing_price:,}원", inline=True)
        embed.add_field(name="새 가격", value=f"{new_price:,}원", inline=True)
        if emoji:
            embed.add_field(name="이모지", value=f"{emoji} (수정됨)", inline=True)
        embed.add_field(name="수정된 파일 수", value=f"{updated_count}개", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
class StockManagementView(nextcord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @nextcord.ui.button(label="카테고리 추가", style=nextcord.ButtonStyle.secondary, custom_id="stock_category_add")
    async def category_add_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.send_modal(CategoryAddModal())
    
    @nextcord.ui.button(label="제품 추가", style=nextcord.ButtonStyle.secondary, custom_id="stock_product_add")
    async def product_add_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        embed = nextcord.Embed(title="📦 제품 추가", color=0x00ff00)
        embed.add_field(name="", value="제품을 추가할 카테고리를 선택하세요.", inline=False)
        await interaction.response.send_message(embed=embed, view=StockCategorySelectView("add"), ephemeral=True)
    
    @nextcord.ui.button(label="카테고리 제거", style=nextcord.ButtonStyle.secondary, custom_id="stock_category_remove")
    async def category_remove_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        embed = nextcord.Embed(title="🗑️ 카테고리 제거", color=0xff6b6b)
        embed.add_field(name="", value="제거할 카테고리를 선택하세요.", inline=False)
        await interaction.response.send_message(embed=embed, view=CategoryRemoveSelectView(), ephemeral=True)
    
    @nextcord.ui.button(label="제품 제거", style=nextcord.ButtonStyle.secondary, custom_id="stock_product_remove")
    async def product_remove_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        embed = nextcord.Embed(title="🗑️ 제품 제거", color=0xff6b6b)
        embed.add_field(name="", value="제품을 제거할 카테고리를 선택하세요.", inline=False)
        await interaction.response.send_message(embed=embed, view=StockCategorySelectView("remove"), ephemeral=True)
    
    @nextcord.ui.button(label="가격수정", style=nextcord.ButtonStyle.secondary, custom_id="stock_price_edit")
    async def price_edit_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        embed = nextcord.Embed(title="💰 가격수정", color=0xffd700)
        embed.add_field(name="", value="가격을 수정할 제품의 카테고리를 선택하세요.", inline=False)
        await interaction.response.send_message(embed=embed, view=StockCategorySelectView("price_edit"), ephemeral=True)
    
    @nextcord.ui.button(label="재고수정", style=nextcord.ButtonStyle.secondary, custom_id="stock_quantity_edit")
    async def stock_edit_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        embed = nextcord.Embed(title="📦 재고수정", color=0x3498db)
        embed.add_field(name="", value="재고를 수정할 제품의 카테고리를 선택하세요.", inline=False)
        await interaction.response.send_message(embed=embed, view=StockCategorySelectView("stock_edit"), ephemeral=True)
    
    @nextcord.ui.button(label="순서수정", style=nextcord.ButtonStyle.secondary, custom_id="stock_order_edit")
    async def order_edit_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        embed = nextcord.Embed(title="📋 제품 순서 수정", color=0x9b59b6)
        embed.add_field(name="", value="순서를 수정할 제품의 카테고리를 선택하세요.", inline=False)
        await interaction.response.send_message(embed=embed, view=StockCategorySelectView("order_edit"), ephemeral=True)
@bot.slash_command(name="임베드재고", description=f"{SERVICE_NAME} | 재고 임베드를 불러옵니다. (관리자 전용)")
async def embed_stock_callback(interaction: nextcord.Interaction,
                               카테고리: str = SlashOption(
                                   description="카테고리 선택 (전체는 'all' 입력)",
                                   required=False)):
    if on_run:
        if interaction.guild is None:
            await interaction.response.send_message("이 명령어는 서버에서만 사용할 수 있습니다.", ephemeral=True)
            return
        
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return
        
        if 카테고리 and 카테고리.lower() == 'all':
            products = get_products_from_stock_folder(interaction.guild.id)
            embed_title = "🛍️ㆍ전체 상품 목록"
            category = 'all'
        elif 카테고리:
            products = get_products_from_category(카테고리)
            embed_title = "🛍️ㆍ제품 목록"
            category = 카테고리
        else:
            embed = nextcord.Embed(title="🛍️ㆍ재고 임베드", color=0xfffffe)
            embed.add_field(name="", value="조회할 상품의 카테고리를 선택하세요.", inline=False)
            await interaction.response.send_message(embed=embed, view=CategorySelectView(interaction.guild.id), ephemeral=True)
            return
        
        if not products:
            embed = nextcord.Embed(title=embed_title, color=0xfffffe)
            embed.add_field(name="", value="등록된 상품이 없습니다.", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = ProductListPaginationView.create_embed(products, category, embed_title, 0)
        view = ProductListPaginationView(products, category, embed_title, 0, None, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view)
@bot.slash_command(name="재고수정", description=f"{SERVICE_NAME} | 재고를 관리합니다.")
async def callback(interaction: nextcord.Interaction,
                   작업: str = SlashOption(
                       description="작업 선택",
                       required=True,
                       choices=["추가", "제거", "가격수정"]),
                   타입: str = SlashOption(
                       description="카테고리 또는 제품",
                       required=True,
                       choices=["카테고리", "제품"]),
                   이름: str = SlashOption(description="카테고리명 또는 제품명", required=True),
                   카테고리: str = SlashOption(description="제품 추가 시 카테고리명 (제품 추가/가격수정 시 필요)", required=False),
                   가격: int = SlashOption(description="가격 (제품 추가 시 필요, 가격수정 시는 모달에서 입력)", required=False)):
    if on_run:
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return
        
        stock_base_dir = 'stock'
        os.makedirs(stock_base_dir, exist_ok=True)
        
        try:
            if 작업 == "추가":
                if 타입 == "카테고리":
                    category_path = os.path.join(stock_base_dir, 이름)
                    if os.path.exists(category_path):
                        await interaction.response.send_message(f"이미 존재하는 카테고리입니다: {이름}", ephemeral=True)
                        return
                    os.makedirs(category_path, exist_ok=True)
                    embed = nextcord.Embed(title="✅ㆍ카테고리 추가 완료", color=0x00ff00)
                    embed.add_field(name="카테고리명", value=이름, inline=False)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    
                elif 타입 == "제품":
                    if not 카테고리:
                        await interaction.response.send_message("제품 추가 시 카테고리명이 필요합니다.", ephemeral=True)
                        return
                    
                    existing_info = get_product_info_from_stock(이름, 카테고리)
                    
                    if not 가격 or 가격 <= 0:
                        if existing_info:
                            await interaction.response.send_modal(StockEditModal(작업, 타입, 이름, 카테고리, existing_info.get('price', 0)))
                        else:
                            await interaction.response.send_message("올바른 가격을 입력해주세요.", ephemeral=True)
                        return
                    
                    category_path = os.path.join(stock_base_dir, 카테고리)
                    if not os.path.exists(category_path):
                        os.makedirs(category_path, exist_ok=True)
                    
                    timestamp = int(datetime.datetime.now().timestamp() * 1000)
                    filename = f"{이름}_{가격}_{timestamp}.txt"
                    file_path = os.path.join(category_path, filename)
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write("")
                    
                    embed = nextcord.Embed(title="✅ㆍ제품 추가 완료", color=0x00ff00)
                    embed.add_field(name="제품명", value=이름, inline=True)
                    embed.add_field(name="카테고리", value=카테고리, inline=True)
                    embed.add_field(name="가격", value=f"{가격:,}원", inline=True)
                    if existing_info:
                        embed.add_field(name="기존 정보", value=f"기존 가격: {existing_info.get('price', 0):,}원", inline=False)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            
            elif 작업 == "제거":
                if 타입 == "카테고리":
                    category_path = os.path.join(stock_base_dir, 이름)
                    if not os.path.exists(category_path):
                        await interaction.response.send_message(f"존재하지 않는 카테고리입니다: {이름}", ephemeral=True)
                        return
                    
                    files = [f for f in os.listdir(category_path) if f.endswith('.txt')]
                    if files:
                        await interaction.response.send_message(f"카테고리 내에 제품이 있어 삭제할 수 없습니다. 먼저 제품을 제거해주세요.", ephemeral=True)
                        return
                    
                    os.rmdir(category_path)
                    embed = nextcord.Embed(title="✅ㆍ카테고리 제거 완료", color=0xff6b6b)
                    embed.add_field(name="카테고리명", value=이름, inline=False)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    
                elif 타입 == "제품":
                    if not 카테고리:
                        await interaction.response.send_message("제품 제거 시 카테고리명이 필요합니다.", ephemeral=True)
                        return
                    
                    category_path = os.path.join(stock_base_dir, 카테고리)
                    if not os.path.exists(category_path):
                        await interaction.response.send_message(f"존재하지 않는 카테고리입니다: {카테고리}", ephemeral=True)
                        return
                    
                    removed_count = 0
                    for filename in os.listdir(category_path):
                        if filename.endswith('.txt'):
                            parsed = parse_filename(filename)
                            file_product_name = parsed['product_name']
                            if file_product_name == 이름:
                                    file_path = os.path.join(category_path, filename)
                                    try:
                                        os.remove(file_path)
                                        removed_count += 1
                                    except Exception as e:
                                        print(f"파일 삭제 오류: {filename} - {e}")
                    
                    if removed_count == 0:
                        await interaction.response.send_message(f"제품을 찾을 수 없습니다: {이름}", ephemeral=True)
                        return
                    
                    embed = nextcord.Embed(title="✅ㆍ제품 제거 완료", color=0xff6b6b)
                    embed.add_field(name="제품명", value=이름, inline=True)
                    embed.add_field(name="카테고리", value=카테고리, inline=True)
                    embed.add_field(name="삭제된 파일 수", value=f"{removed_count}개", inline=True)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            
            elif 작업 == "가격수정":
                if 타입 != "제품":
                    await interaction.response.send_message("가격수정은 제품에만 적용할 수 있습니다.", ephemeral=True)
                    return
                
                if not 카테고리:
                    await interaction.response.send_message("가격수정 시 카테고리명이 필요합니다.", ephemeral=True)
                    return
                
                existing_info = get_product_info_from_stock(이름, 카테고리)
                if not existing_info:
                    await interaction.response.send_message(f"제품을 찾을 수 없습니다: {이름}", ephemeral=True)
                    return
                
                await interaction.response.send_modal(StockEditModal(작업, 타입, 이름, 카테고리, existing_info.get('price', 0)))
                return
        
        except Exception as e:
            await interaction.response.send_message(f"작업 중 오류가 발생했습니다: {str(e)}", ephemeral=True)

@bot.slash_command(name="리셀러설정", description=f"{SERVICE_NAME} | 사용자에게 리셀러 역할을 부여합니다. (관리자 전용)")
async def reseller_set_command(interaction: nextcord.Interaction, 멤버: nextcord.Member):
    if on_run:
        if interaction.user.id not in admin_ids:
            await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return
        
        try:
            reseller_role = interaction.guild.get_role(RESELLER_ROLE_ID)
            if not reseller_role:
                await interaction.response.send_message(f"리셀러 역할을 찾을 수 없습니다. (역할 ID: {RESELLER_ROLE_ID})", ephemeral=True)
                return
            
            has_role = reseller_role in 멤버.roles
            
            if has_role:
                await 멤버.remove_roles(reseller_role)
                action = "제거"
                action_text = "리셀러 역할이 제거되었습니다."
            else:
                await 멤버.add_roles(reseller_role)
                action = "부여"
                action_text = "리셀러 역할이 부여되었습니다."
            
            embed = nextcord.Embed(title="✅ 리셀러 역할 설정 완료", color=0x00ff00)
            embed.add_field(name="대상 사용자", value=f"**{멤버.name}** ({멤버.mention})", inline=False)
            embed.add_field(name="작업", value=action, inline=True)
            embed.add_field(name="상태", value=action_text, inline=True)
            embed.add_field(name="혜택", value="리셀러는 모든 충전 시 20% 추가 충전 혜택을 받습니다.", inline=False)
            embed.set_thumbnail(url=멤버.display_avatar.url)
            embed.set_footer(text=f"관리자: {interaction.user.name} | ID: {멤버.id}")
            embed.timestamp = datetime.datetime.now()
            
            await interaction.response.send_message(embed=embed)
            
        except nextcord.errors.Forbidden:
            await interaction.response.send_message("봇에게 역할을 관리할 권한이 없습니다.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"리셀러 역할 설정 중 오류가 발생했습니다: {str(e)}", ephemeral=True)

@bot.slash_command(name="관리자설정", description=f"{SERVICE_NAME} | 관리자 권한을 부여하거나 제거합니다. (최고 관리자 전용)")
async def admin_set_command(interaction: nextcord.Interaction, 멤버: nextcord.Member):
    global admin_ids
    if on_run:
        if len(admin_ids) == 0 or interaction.user.id != admin_ids[0]:
            await interaction.response.send_message("최고 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return
        
        try:
            target_id = 멤버.id
            
            if target_id in admin_ids:
                admin_ids.remove(target_id)
                save_admin_ids(admin_ids)
                action = "제거"
                action_text = "관리자 권한이 제거되었습니다."
            else:
                admin_ids.append(target_id)
                save_admin_ids(admin_ids)
                action = "부여"
                action_text = "관리자 권한이 부여되었습니다."
            
            embed = nextcord.Embed(title="✅ 관리자 권한 설정 완료", color=0x00ff00)
            embed.add_field(name="대상 사용자", value=f"**{멤버.name}** ({멤버.mention})", inline=False)
            embed.add_field(name="작업", value=action, inline=True)
            embed.add_field(name="상태", value=action_text, inline=True)
            embed.add_field(name="현재 관리자 수", value=f"{len(admin_ids)}명", inline=False)
            embed.add_field(name="관리자 권한", value="• 봇 자판기 관리\n• 재고 관리\n• 잔액 관리\n• 충전 승인\n• 계좌 설정 등", inline=False)
            embed.set_thumbnail(url=멤버.display_avatar.url)
            embed.set_footer(text=f"설정자: {interaction.user.name} | 대상 ID: {target_id}")
            embed.timestamp = datetime.datetime.now()
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"관리자 권한 설정 중 오류가 발생했습니다: {str(e)}", ephemeral=True)

@bot.event
async def on_ready():
    
    total_members = 0
    for guild in bot.guilds:
        total_members += guild.member_count
    
    activity = nextcord.Activity(
        type=nextcord.ActivityType.watching,
        name=RPC_MESSAGES[0]
    )
    await bot.change_presence(activity=activity)
    
    print(f" | {bot.user}으로 로그인됨 (ID: {bot.user.id})")
    print(f" | {len(bot.guilds)}개 서버에서 {total_members:,}명에게 서비스 제공중")
    print(f" | RPC 상태:  | 24시간 영업중")
    
    bot.loop.create_task(stock_monitor())
    bot.loop.create_task(setup_vending_on_ready())
    bot.loop.create_task(update_rpc_status())
    bot.loop.create_task(pending_charge_timeout_monitor())
    bot.loop.create_task(setup_stock_management_on_ready())
    bot.loop.create_task(pushbullet_notification_monitor())
async def update_rpc_status():
    while True:
        try:
            total_members = 0
            for guild in bot.guilds:
                total_members += guild.member_count
            rpc_message = RPC_MESSAGES[0]
            activity_types = [
                nextcord.ActivityType.watching,
                nextcord.ActivityType.playing,
                nextcord.ActivityType.listening,
                nextcord.ActivityType.streaming
            ]
            activity_type = random.choice(activity_types)
            activity = nextcord.Activity(
                type=activity_type,
                name=rpc_message
            )
            await bot.change_presence(activity=activity)
            
            print(f" | RPC 상태 업데이트: {rpc_message}")
            
            await asyncio.sleep(RPC_UPDATE_INTERVAL)
            
        except Exception as e:
            print(f" | RPC 상태 업데이트 오류: {e}")
            await asyncio.sleep(RPC_ERROR_RETRY_INTERVAL)
async def stock_monitor():
    stock_counts = {}
    
    stock_base_dir = 'stock'
    
    def get_all_stock_files():
        """모든 재고 파일 경로를 반환합니다 (카테고리 포함)."""
        files = {}
        if not os.path.exists(stock_base_dir):
            return files
        
        categories = get_categories_from_stock_folder()
        for category in categories:
            category_path = os.path.join(stock_base_dir, category)
            if os.path.exists(category_path) and os.path.isdir(category_path):
                for filename in os.listdir(category_path):
                    if filename.endswith('.txt'):
                        file_key = f"{category}/{filename}"
                        file_path = os.path.join(category_path, filename)
                        files[file_key] = {'path': file_path, 'category': category, 'filename': filename}
        
        for filename in os.listdir(stock_base_dir):
            if filename.endswith('.txt'):
                file_path = os.path.join(stock_base_dir, filename)
                if os.path.isfile(file_path):
                    files[filename] = {'path': file_path, 'category': None, 'filename': filename}
        
        return files
    
    all_files = get_all_stock_files()
    for file_key, file_info in all_files.items():
        try:
            with open(file_info['path'], 'r', encoding='utf-8') as f:
                lines = f.readlines()
                stock_counts[file_key] = len([line.strip() for line in lines if line.strip()])
        except:
            stock_counts[file_key] = 0
    
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            if not os.path.exists(stock_base_dir):
                await asyncio.sleep(30)
                continue
            
            current_files = get_all_stock_files()
            
            for file_key, file_info in current_files.items():
                try:
                    with open(file_info['path'], 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        current_count = len([line.strip() for line in lines if line.strip()])
                    
                    parsed = parse_filename(file_info['filename'])
                    product_name = parsed['product_name']
                    price = parsed['price']
                    category = file_info['category']
                    
                    if file_key in stock_counts:
                        old_count = stock_counts[file_key]
                        if current_count > old_count:
                            added_count = current_count - old_count
                            
                            if price > 0:
                                price_str = f"{price:,}원"
                                title = f"{product_name} [{price_str}]"
                            else:
                                title = product_name
                            
                            image_url = get_product_image_url(product_name, category)
                            
                            stock_log_channel = bot.get_channel(STOCK_LOG_CHANNEL_ID)
                            if stock_log_channel:
                                embed = nextcord.Embed(
                                    title=title,
                                    description=f"상품이 **{added_count}개** 입고되었습니다.",
                                    color=0x8B5CF6  # 보라색 계열
                                )
                                
                                if image_url:
                                    embed.set_image(url=image_url)
                                
                                embed.timestamp = datetime.datetime.now()
                                await stock_log_channel.send(embed=embed)
                            
                            admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
                            if admin_channel:
                                admin_embed = nextcord.Embed(
                                    title=f"📦 관리자 자동 입고 로그 - {title}",
                                    color=0xffd700
                                )
                                admin_embed.add_field(name="추가된 재고", value=f"{added_count}개", inline=True)
                                admin_embed.add_field(name="현재 재고", value=f"{current_count}개", inline=True)
                                admin_embed.timestamp = datetime.datetime.now()
                                admin_embed.set_footer(text=f"파일: {file_info['filename']}")
                                await admin_channel.send(embed=admin_embed)
                    else:
                        if current_count > 0:
                            if price > 0:
                                price_str = f"{price:,}원"
                                title = f"{product_name} [{price_str}]"
                            else:
                                title = product_name
                            
                            image_url = get_product_image_url(product_name, category)
                            
                            stock_log_channel = bot.get_channel(STOCK_LOG_CHANNEL_ID)
                            if stock_log_channel:
                                embed = nextcord.Embed(
                                    title=title,
                                    description=f"상품이 **{current_count}개** 입고되었습니다.",
                                    color=0x8B5CF6  # 보라색 계열
                                )
                                
                                if image_url:
                                    embed.set_image(url=image_url)
                                
                                embed.timestamp = datetime.datetime.now()
                                await stock_log_channel.send(embed=embed)
                            
                            admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
                            if admin_channel:
                                admin_embed = nextcord.Embed(
                                    title=f"📦 관리자 신규 제품 로그 - {title}",
                                    color=0xffd700
                                )
                                admin_embed.add_field(name="재고", value=f"{current_count}개", inline=True)
                                admin_embed.timestamp = datetime.datetime.now()
                                admin_embed.set_footer(text=f"파일: {file_info['filename']}")
                                await admin_channel.send(embed=admin_embed)
                    
                    stock_counts[file_key] = current_count
                except Exception as e:
                    print(f"파일 읽기 오류: {file_key} - {e}")
            
            deleted_files = set(stock_counts.keys()) - set(current_files.keys())
            for file_key in deleted_files:
                del stock_counts[file_key]
            
        except Exception as e:
            print(f"재고 모니터링 오류: {e}")
        
        await asyncio.sleep(30)
async def setup_stock_management_on_ready():
    await bot.wait_until_ready()
    try:
        channel = bot.get_channel(STOCK_MANAGEMENT_CHANNEL_ID)
        if not channel or not isinstance(channel, nextcord.TextChannel):
            return
        
        try:
            await channel.purge(limit=None)
        except Exception:
            async for msg in channel.history(limit=None):
                try:
                    await msg.delete()
                except Exception:
                    pass
        
        embed = nextcord.Embed(title="📦 재고 관리", color=0x00ff00)
        safe_add_field(embed, "", "재고수정 버튼을 사용하여 재고를 관리하세요.", inline=False)
        safe_add_field(embed, "카테고리 추가", "카테고리 추가 버튼을 눌러 새로운 카테고리를 추가합니다.", inline=False)
        safe_add_field(embed, "제품 추가", "제품 추가 버튼을 눌러 새로운 제품을 추가합니다.", inline=False)
        safe_add_field(embed, "카테고리 제거", "카테고리 제거 버튼을 눌러 카테고리를 삭제합니다.", inline=False)
        safe_add_field(embed, "제품 제거", "제품 제거 버튼을 눌러 제품을 삭제합니다.", inline=False)
        safe_add_field(embed, "가격수정", "가격수정 버튼을 눌러 제품 가격을 수정합니다.", inline=False)
        
        await channel.send(embed=embed, view=StockManagementView())
    except Exception as e:
        print(f"재고수정 채널 설정 실패: {e}")
async def setup_vending_on_ready():
    await bot.wait_until_ready()
    for channel_id in AUTO_VENDING_CHANNEL_IDS:
        try:
            channel = bot.get_channel(channel_id)
            if not channel or not isinstance(channel, nextcord.TextChannel):
                continue
            try:
                async for msg in channel.history(limit=None):
                    try:
                        if msg.author == bot.user or msg.author.id == bot.user.id:
                            await msg.delete()
                    except Exception:
                        pass
            except Exception:
                pass
            embed = nextcord.Embed(title="** 🔔 개미몰 봇자판기 **", description=VENDING_MACHINE_DESCRIPTION, color=0xfffffe)
            if VENDING_MACHINE_IMAGE_ENABLED:
                embed.set_image(url=VENDING_MACHINE_IMAGE_URL)
            await channel.send(embed=embed, view=ProductListView(guild_id=channel.guild.id))
        except Exception as e:
            print(f"자판기 자동 전송 실패: {channel_id} - {e}")
@bot.event
async def on_message(message):
    if isinstance(message.channel, nextcord.TextChannel) and message.channel.id == CHARGE_LOG_CHANNEL_ID:
        try:
            if message.id in PROCESSED_CHARGE_MESSAGE_IDS:
                return
            
            if message.attachments:
                image_url = None
                for attachment in message.attachments:
                    if attachment.content_type and attachment.content_type.startswith('image/'):
                        image_url = attachment.url
                        break
                
                if image_url:
                    if message.author.bot:
                        return
                    
                    match_user_id = None
                    match_info = None
                    
                    sorted_charges = sorted(PENDING_CHARGES.items(), key=lambda x: x[1].get("timestamp", 0), reverse=True)
                    
                    for uid, info in sorted_charges:
                        if info.get("image_sent", False):
                            continue
                        match_user_id = uid
                        match_info = info
                        break
                    
                    if match_user_id and match_info:
                        amount = match_info.get("amount", 0)
                        depositor_name = match_info.get("depositor_name", "알 수 없음")
                        
                        guild_id = list(bot.guilds)[0].id if bot.guilds else None
                        if guild_id:
                            log_index = add_charge_log(guild_id, match_user_id, amount, status="대기중", method="계좌이체", depositor_name=depositor_name, receipt_image=image_url)
                            
                            view = ImageChargeApprovalView(match_user_id, amount, log_index, depositor_name, image_url)
                            
                            image_embed = nextcord.Embed(title="📸 입금내역 확인 요청", color=0x00b894)
                            image_embed.add_field(name="사용자", value=f"<@{match_user_id}>", inline=True)
                            image_embed.add_field(name="입금자명", value=depositor_name, inline=True)
                            image_embed.add_field(name="금액", value=f"{amount:,}원", inline=True)
                            image_embed.add_field(name="안내", value="입금내역 사진을 확인 후 승인 또는 거절해주세요.", inline=False)
                            image_embed.set_image(url=image_url)
                            image_embed.timestamp = datetime.datetime.now()
                            
                            await message.channel.send(embed=image_embed, view=view)
                            
                            match_info["image_sent"] = True
                            PENDING_CHARGES[match_user_id] = match_info
                            PROCESSED_CHARGE_MESSAGE_IDS.add(message.id)
                            return
            
            content = message.content or ""
            if not content:
                return
            import re
            amt_match = re.search(r"입금\s*([\d,]+)원", content)
            if not amt_match:
                return
            amount = int(amt_match.group(1).replace(",", ""))
            lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
            depositor = None
            
            def is_valid_depositor_name(line: str) -> bool:
                if not re.search(r"[가-힣]", line):
                    return False
                if "(" in line or ")" in line:
                    return False
                if "*" in line:
                    return False
                if re.search(r"\d", line):
                    return False
                if "원" in line or "잔액" in line:
                    return False
                if line.startswith("["):
                    return False
                normalized = re.sub(r"[^가-힣]", "", line)
                if len(normalized) < 2 or len(normalized) > 4:
                    return False
                return True
            
            for i, ln in enumerate(lines):
                if "입금" in ln and i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if is_valid_depositor_name(next_line):
                        depositor = next_line
                        break
            
            if depositor is None:
                for i, ln in enumerate(lines):
                    if ln.startswith("잔액") and i > 0:
                        prev_line = lines[i-1]
                        if is_valid_depositor_name(prev_line):
                            depositor = prev_line
                            break
            
            if depositor is None:
                for ln in reversed(lines):
                    if is_valid_depositor_name(ln):
                        depositor = ln
                        break
            
            if not depositor:
                return
            
            def normalize_name(n: str) -> str:
                normalized = re.sub(r"[^가-힣]", "", n)
                bank_words = ["입출금통장", "통장", "계좌", "입금", "출금"]
                for word in bank_words:
                    normalized = normalized.replace(word, "")
                return normalized
            
            def names_match(name1: str, name2: str) -> bool:
                norm1 = normalize_name(name1)
                norm2 = normalize_name(name2)
                if norm1 == norm2 or name1.strip() == name2.strip():
                    return True
                if norm1 in norm2 or norm2 in norm1:
                    min_len = min(len(norm1), len(norm2))
                    if min_len >= 2:
                        return True
                if len(norm1) >= 2 and len(norm2) >= 2:
                    if norm1[0] == norm2[0]:
                        if len(norm1) == len(norm2) or abs(len(norm1) - len(norm2)) <= 1:
                            if norm1[-1] == norm2[-1]:
                                return True
                            if len(norm1) >= 2 and len(norm2) >= 2:
                                if norm1[:2] == norm2[:2]:
                                    return True
                return False
            
            parsed_norm = normalize_name(depositor)
            cleanup_old_pending_charges()
            match_user_id = None
            for uid, info in PENDING_CHARGES.items():
                pending_name = str(info.get("depositor_name", ""))
                if info.get("amount") == amount:
                    if names_match(pending_name, depositor):
                        match_user_id = uid
                        break
            
            if not match_user_id:
                print(f"자동승인 매칭 실패 - 금액: {amount}원, 추출된 입금자명: '{depositor}', 대기중인 요청: {[(uid, info.get('depositor_name'), info.get('amount')) for uid, info in PENDING_CHARGES.items()]}")
                return
            guild_id = list(bot.guilds)[0].id
            credited_amount = amount
            user_data = get_user_data(guild_id, match_user_id)
            user_data['balance'] = safe_add(user_data['balance'], credited_amount)
            save_user_data(load_user_data())
            update_user_data(guild_id, match_user_id, user_data)
            
            def normalize_depositor_name(name: str) -> str:
                normalized = re.sub(r"[^가-힣]", "", name)
                bank_words = ["입출금통장", "통장", "계좌", "입금", "출금"]
                for word in bank_words:
                    normalized = normalized.replace(word, "")
                return normalized.strip() if normalized.strip() else name
            
            clean_depositor = normalize_depositor_name(depositor)
            add_deposit_record(guild_id, match_user_id, credited_amount, method="계좌이체", depositor_name=clean_depositor)
            try:
                member = bot.get_user(match_user_id)
                if member:
                    dm = nextcord.Embed(title="승인되었습니다", color=0x00ff00)
                    dm.add_field(name="입금자명", value=clean_depositor, inline=True)
                    dm.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
                    dm.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
                    await member.send(embed=dm)
            except Exception:
                pass
            ok = nextcord.Embed(title="승인되었습니다", color=0x2ecc71)
            ok.add_field(name="입금자명", value=clean_depositor, inline=True)
            ok.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
            ok.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
            ok.add_field(name="사용자", value=f"<@{match_user_id}>", inline=False)
            await message.channel.send(embed=ok)
            
            try:
                charge_request_channel = bot.get_channel(CHARGE_REQUEST_CHANNEL_ID)
                if charge_request_channel:
                    request_ok = nextcord.Embed(title="승인되었습니다", color=0x2ecc71)
                    request_ok.add_field(name="입금자명", value=clean_depositor, inline=True)
                    request_ok.add_field(name="총 충전 금액", value=f"{credited_amount:,}원", inline=True)
                    request_ok.add_field(name="충전 후 잔액", value=f"{user_data['balance']:,}원", inline=True)
                    request_ok.add_field(name="사용자", value=f"<@{match_user_id}>", inline=False)
                    await charge_request_channel.send(embed=request_ok)
            except Exception:
                pass
            PROCESSED_CHARGE_MESSAGE_IDS.add(message.id)
            
            try:
                charge_info = PENDING_CHARGES.get(match_user_id, {})
                request_message_id = charge_info.get("message_id")
                if request_message_id:
                    req_channel = bot.get_channel(BANK_REQUEST_CHANNEL_ID)
                    if req_channel:
                        try:
                            request_msg = await req_channel.fetch_message(request_message_id)
                            if request_msg and request_msg.components:
                                disabled_view = nextcord.ui.View(timeout=None)
                                for component in request_msg.components:
                                    for item in component.children:
                                        if isinstance(item, nextcord.ui.Button):
                                            disabled_btn = nextcord.ui.Button(
                                                label=item.label or "승인",
                                                style=item.style,
                                                emoji=item.emoji if item.emoji else None,
                                                disabled=True,
                                                custom_id=item.custom_id
                                            )
                                            disabled_view.add_item(disabled_btn)
                                await request_msg.edit(view=disabled_view)
                        except (nextcord.errors.NotFound, nextcord.errors.HTTPException) as e:
                            print(f"충전 요청 메시지 버튼 비활성화 실패: {e}")
            except Exception as e:
                print(f"자동 승인 버튼 비활성화 오류: {e}")
            try:
                del PENDING_CHARGES[match_user_id]
            except Exception:
                pass
            return
        except Exception as e:
            print(f"웹훅 자동승인 처리 오류: {e}")
            return
    
    await bot.process_commands(message)
bot.run(discordBotToken)