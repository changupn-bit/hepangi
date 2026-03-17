
# import requests

# while True:
#     requests.post("https://api.pushbullet.com/v2/pushes", auth=('o.fEwRQ3Kqe2T5wS68Ya3WsuJGEpoB52Dv', 'o.fEwRQ3Kqe2T5wS68Ya3WsuJGEpoB52Dv'))
#     # o.fEwRQ3Kqe2T5wS68Ya3WsuJGEpoB52Dv

# wss://stream.pushbullet.com/websocket/o.fEwRQ3Kqe2T5wS68Ya3WsuJGEpoB52Dv


import websocket, json
from tools import database
bankpin = "o.szuDBMy6uNCuGGlb8eK6lvq9NVc3Z0xQ"


try:
    import thread
except ImportError:
    import _thread as thread
import time

def on_message(ws, message):
    print("message:",message)
    try:
        obj = json.loads(message)
        if obj["type"] == "push":
            push = obj["push"]
            body = push["body"].replace("\n"," ")
            site_id = database.select("sites", bankpin=bankpin)[0][0]
            NotificationApplicationName = str(push["package_name"])
            message = body.replace("원", "").replace(",", "").split(' ')
            displayname = ""
            count = 0
            print(f"BankAPI[SUCCESS]: \nbody: {push['body']}\nNotificationApplicationName: {NotificationApplicationName}")
            if NotificationApplicationName == "com.IBK.SmartPush.app":

                
                sp = body.split(" ")
                displayname = sp[2]
                count = int(sp[1].replace("원", "").replace(",",""))
                print(f"BankAPI[SUCCESS]: com.IBK.SmartPush.app")
            elif NotificationApplicationName == "com.nh.mobilenoti":
                displayname = message[5]
                count = message[1].replace("입금", "").replace("원", "").replace(",","")
                count = int(count)
                print(f"BankAPI[SUCCESS]: com.nh.mobilenoti")
            elif NotificationApplicationName == "com.wooribank.smart.npib":
                sp = body.split(" ")
                displayname = sp[1]
                count = int(sp[5].replace("원", "").replace(",",""))
                print(f"BankAPI[SUCCESS]: com.wooribank.smart.npib")
            elif NotificationApplicationName == "com.kakaobank.channel":
                name = body.split(" ")
                
                displayname = name[5]
                count = int(name[4].replace(",", "").replace("원", ""))
                print(f"BankAPI[SUCCESS]: com.kakaobank.channel")
            else:
                print(f"BankAPI[ERROR]: not found NotificationApplicationName")
                return
            print(f"BankAPI[SUCCESS]: \nSite_ID: {site_id}\nBankName: {displayname}\nAmount: {count}")
            database.update("user", "money", int(database.select("user", sites=site_id, bankname=displayname)[0][4]) + count, bankname=displayname)
    except Exception as e:
        print(f"BankAPI[ERROR]: {e}")
def on_error(ws, error):
    print("error:",error)

def on_close(ws):
    print("### closed ###")

def on_open(ws):
    print("Opened")
    

if __name__ == "__main__":
    websocket.enableTrace(True)
    
    ws = websocket.WebSocketApp("wss://stream.pushbullet.com/websocket/"+bankpin,
                              on_message = on_message,
                              on_error = on_error,
                              on_close = on_close)
    ws.on_open = on_open
    ws.run_forever()
    
