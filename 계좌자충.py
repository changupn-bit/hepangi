import websocket, json, asyncio
from flask import Flask, render_template, request, session, redirect

app = Flask(__name__)

@app.route("/api", methods=["POST"])
def _charge():
    req = request.get_json()
    bankpin = req.get("bankpin")
    username = req.get("userinfo")
    
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
                if displayname == username:
                    if count == req.get("amount"):
                        print(f"BankAPI[SUCCESS]: BankName: {displayname}\nAmount: {count}")
                        return {"result": True, "amount": count}
                    else:
                        return
                else:
                    return
                
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
    
app.run()