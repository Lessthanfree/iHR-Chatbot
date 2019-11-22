import threading,re,os
from win32gui import *
from win32api import *
from win32clipboard import *
from win32con import *
from time import *
from jpype import *
from chatbot import Chatbot
import pandas as pd

clipboard_sleep = 2
cmd_sleep = 0.05
self_userID = "temporary"

GLOBAL = {}

def find_handle(userid):
    #spy++ | hard coded have to update if qianniu update their UI
    a = FindWindow("StandardFrame",userid + " - 接待中心")
    aa = FindWindowEx(a, 0, "StandardWindow", "")
    aaa = FindWindowEx(aa, 0, "StandardWindow", "")
    aaa = FindWindowEx(aa, aaa, "StandardWindow", "")
    aaa = FindWindowEx(aa, aaa, "StandardWindow", "")
    aaaa = FindWindowEx(aaa, 0, "SplitterBar", "")

    b = FindWindowEx(aaaa, 0, "StandardWindow", "")
    bb = FindWindowEx(aaaa, b, "StandardWindow", "")
    QN_input_hwnd = FindWindowEx(bb,0,"RichEditComponent", "")

    c = FindWindowEx(b, 0, "PrivateWebCtrl", "")
    cc = FindWindowEx(c,0,"Aef_WidgetWin_0","")
    QN_output_hwnd = FindWindowEx(cc,0,"Aef_RenderWidgetHostHWND", "Chrome Legacy Window")

    QN_sendBut_hwnd = FindWindowEx(bb,0,"StandardButton", "发送")

    return QN_input_hwnd,QN_output_hwnd,QN_sendBut_hwnd

def save2troubleshoot(right,wrong,query,intent,slot,id):
    df = pd.read_csv(r"troubleshoot.csv",encoding="gb18030")
    list_list=df.values.tolist()
    
    list_list.append([wrong,id,query,right,intent,slot])

    new_df = pd.DataFrame(data=list_list)
    new_df.to_csv(r"troubleshoot.csv",encoding="gb18030",index=0,header=0)

def send_message_QN(text,QN_input_hwnd,QN_sendBut_hwnd,query,reply_template,custID,mode):
    #list of keybdEvents
    #https://blog.csdn.net/zhanglidn013/article/details/35988381

    # Paste text into the chatbox
    SendMessage(QN_input_hwnd, 0x000C, 0, text)

    if mode == "":
        # AUTO SEND MODE
        SendMessage(QN_sendBut_hwnd, 0xF5, 0, 0)
        print("Message Sent: {}".format(text))
    else:
        # CONFIRMATION MODE
        sleep(1)
        return

        # -- EVERYTHING BELOW HERE DOESNT HAPPEN -- 
        confirm = input("如果回复是对的请按回车键,不然请输入对的回答:  ")
        if confirm == "":
            #send text
            SendMessage(QN_sendBut_hwnd, 0xF5, 0, 0)
            print("Message Sent: {}".format(text))
        else:
            SendMessage(QN_input_hwnd, 0x000C, 0, confirm)
            SendMessage(QN_sendBut_hwnd, 0xF5, 0, 0)
            print("Message Sent: {}".format(text))
            save2troubleshoot(confirm,text,query,str(reply_template[1]),str(reply_template[2]),custID)

def setActiveScreen(QN_output_hwnd):
    SetForegroundWindow(QN_output_hwnd)

    rect = GetWindowRect(QN_output_hwnd)
    SetCursorPos((rect[2]-20,rect[1]+10))
    
    sleep(cmd_sleep)
    mouse_event(MOUSEEVENTF_LEFTDOWN,0,0,0,0)
    mouse_event(MOUSEEVENTF_LEFTUP,0,0,0,0)
    sleep(cmd_sleep)

def select_copy():
    #ctrl a
    keybd_event(17, 0, 0, 0)
    keybd_event(65, 0, 0, 0)
    sleep(cmd_sleep)
    #ctrl a release
    keybd_event(65, 0, 2, 0)
    keybd_event(17, 0, 2, 0)

    #ctrl c
    sleep(cmd_sleep)
    keybd_event(17, 0, 0, 0)
    keybd_event(67, 0, 0, 0)
    sleep(cmd_sleep)
    # ctrl c release 
    keybd_event(67, 0, 2, 0)
    keybd_event(17, 0, 2, 0)
    sleep(cmd_sleep)
    
def getRawText():
    rpt = 0
    succeed = False
    while not succeed and rpt < 5:
        try:
            OpenClipboard()
            succeed = True
        except Exception as e:
            print("OPEN CLIPBOARD EXCEPTION:",e)
            print("Trying again...")
        rpt += 1

    sleep(0.05)

    rpt = 0
    raw_text = ""
    while raw_text == "" and rpt < 5:
        try:
            raw_text = GetClipboardData()
        except Exception as e:
            print("GET CLIPBOARD EXCEPTION:",e)
            print("Trying again...")
        rpt += 1

    sleep(0.05)

    rpt = 0
    succeed = False
    while not succeed and rpt < 5:
        try:
            CloseClipboard()
            succeed = True
        except Exception as e:
            print("CLOSE CLIPBOARD EXCEPTION:",e)
            print("Trying again...")
        rpt += 1

    sleep(0.05)
    sleep(clipboard_sleep)
    raw_text_list = raw_text.splitlines()
    processed_text_list = []
    for sent in raw_text_list:
        sent = sent.strip()
        if sent != "" and sent != "以上为历史消息":
            processed_text_list.append(sent)
    processed_text_list.reverse()
    return processed_text_list

def check_if_edited(last_sent, messages, q, cid):

    last_bot_reply = GLOBAL.get("last_bot_reply","")
    print("<LAST SENT>",last_sent,"bot wanted to reply:",last_bot_reply)
    if not last_bot_reply == last_sent and not last_bot_reply == "":
        save2troubleshoot(str(last_sent), str(last_bot_reply), str(q), "intent", "slot info",str(cid))
    return

def processText(self_userID,rawText):
    date_time_pattern = re.compile(r"\d*-\d*-\d* \d{2}:\d{2}:\d{2}")
    idx = 0
    prevs_idx = 0
    query_list = []
    custid = ""
    for sent in rawText:
        if re.search(date_time_pattern,sent):
            if re.search(self_userID,sent):
                last_sent = rawText[idx-1]
                break
            else:
                custid = re.sub(date_time_pattern,"",sent)
                for i in range(prevs_idx,idx):
                    query_list.append(rawText[i])
                prevs_idx = idx + 1
        idx += 1
    query_list.reverse()
    query = " ".join(query_list)
    check_if_edited(last_sent,query_list, query, custid)
    return query,custid

def check_new_message(self_userID,QN_output_hwnd):
    print('Checking for new messages...')
    setActiveScreen(QN_output_hwnd)
    select_copy()
    rawText = getRawText()
    query,cust_QN_ID = processText(self_userID,rawText)
    print("Customer ID: {} Query: {}".format(cust_QN_ID, query))
    return query, cust_QN_ID

#insert image path here for the series of place for the OCR to click on
def SeekNewMessage(clickImage):
    print("Finding new chat...")

    Screen = JClass('org.sikuli.script.Screen')
    screen = Screen()

    try:
        screen.click(clickImage)
    except Exception:
        print("No new chat")

def main(text_in_hwnd,text_out_hwnd,button_hwnd,self_userID,bot,SeekImagePath,mode):   

    query, custID = check_new_message(self_userID,text_out_hwnd)
    
    if not query == "":
        reply_template = bot.get_bot_reply(custID,query)
        reply = reply_template[0]
        GLOBAL["last_bot_reply"] = reply
        if type(reply) == list:
            for r in reply:
                send_message_QN(r,text_in_hwnd,button_hwnd,query,reply_template,custID,mode)
        else:
            send_message_QN(reply,text_in_hwnd,button_hwnd,query,reply_template,custID,mode)
    
    SeekNewMessage(SeekImagePath)

    #timer = threading.Timer(10,main,[text_in_hwnd,text_out_hwnd,button_hwnd,self_userID,bot,SeekImagePath])
    #add something to stop the program
    #timer.start()

if __name__ == "__main__":
    self_userID = "女人罪爱:小梅"
    delay_time = input("Enter the delay time (in seconds) for each cycle to look for new message 投入延期(秒钟)): ")
    #enter for testing, 1 for deployment
    mode = input("Enter the mode 投入模式: ")
    GLOBAL["mode"] = 1 if mode == "" else 0
    try:    
        text_in_hwnd,text_out_hwnd,button_hwnd = find_handle(self_userID)
    except Exception:
        print("Window Handle cannot be found!")

    projectDIR = os.getcwd()
    #set JAVA path
    defaultJVMpath = (r"C:\Program Files\Java\jdk-12.0.2\bin\server\jvm.dll")
    jarPath = "-Djava.class.path=" + os.path.join(projectDIR,r"sikuliX\sikulixapi.jar")
    SeekImagePath = os.path.join(projectDIR,r"sikuliX\A.PNG")

    print("Starting JVM...")
    startJVM(defaultJVMpath,'-ea',jarPath,convertStrings=False)
    java.lang.System.out.println("Started JVM!")

    bot = Chatbot()
    bot.start()
    
    print("Starting program....") 
    while True:
        main(text_in_hwnd,text_out_hwnd,button_hwnd,self_userID,bot,SeekImagePath,mode)
        sleep(float(delay_time))