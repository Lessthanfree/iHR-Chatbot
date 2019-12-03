import threading,re,os,time,traceback,datetime
import win32gui, win32api, win32clipboard, win32con, jpype
from chatbot import Chatbot
import pandas as pd

GLOBAL = {}

clipboard_sleep = 0.05
cmd_sleep = 0.05
GLOBAL["human_input_sleep"] = 5
self_userID = "temporary"

KEY_PRESS = 0
KEY_LETGO = 2

GLOBAL["today_date"] = str(datetime.datetime.now().date())
GLOBAL["last_query"] = ""
GLOBAL["last_query_time"] = ""
GLOBAL["self_last_sent_msg"] = ""
GLOBAL["got_new_message"] = True
GLOBAL["new_chat_check_interval"] = 3

class QianNiuWindow:
    def __init__(self):
        self.main_window = None
        self.send_but = None
        self.input_dlg = None
        self.msg_dlg = None
        self.userID = "女人罪爱" # HARDCODED. More general so that you don't catch 同事

    def SetAsForegroundWindow(self):
        # First, make sure all (other) always-on-top windows are hidden.
        self.hide_always_on_top_windows()
        win32gui.SetForegroundWindow(self.main_window)
    def Maximize(self):
        win32gui.ShowWindow(self.main_window, win32con.SW_NORMAL)
    def _window_enum_callback(self, hwnd, regex):
        '''Pass to win32gui.EnumWindows() to check all open windows'''
        if self.main_window is None and re.match(regex, str(win32gui.GetWindowText(hwnd))) is not None:
            self.main_window = hwnd
            # self.userID = re.match(regex,str(win32gui.GetWindowText(hwnd)))[0] # DISABLED
    def find_window_regex(self, regex):
        self.main_window = None
        win32gui.EnumWindows(self._window_enum_callback, regex)
    def hide_always_on_top_windows(self):
        win32gui.EnumWindows(self._window_enum_callback_hide, None)
    def _window_enum_callback_hide(self, hwnd, unused):
        if hwnd != self.main_window: # ignore self
            # Is the window visible and marked as an always-on-top (topmost) window?
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST:
                # Ignore windows of class 'Button' (the Start button overlay) and
                # 'Shell_TrayWnd' (the Task Bar).
                className = win32gui.GetClassName(hwnd)
                if not (className == 'Button' or className == 'Shell_TrayWnd'):
                    # Force-minimize the window.
                    # Fortunately, this seems to work even with windows that
                    # have no Minimize button.
                    # Note that if we tried to hide the window with SW_HIDE,
                    # it would disappear from the Task Bar as well.
                    win32gui.ShowWindow(hwnd, win32con.SW_FORCEMINIMIZE)
    def find_handle(self):
        aa = win32gui.FindWindowEx(self.main_window, 0, "StandardWindow", "")
        aaa = win32gui.FindWindowEx(aa, 0, "StandardWindow", "")
        aaa = win32gui.FindWindowEx(aa, aaa, "StandardWindow", "")
        aaa = win32gui.FindWindowEx(aa, aaa, "StandardWindow", "")
        aaaa = win32gui.FindWindowEx(aaa, 0, "SplitterBar", "")

        b = win32gui.FindWindowEx(aaaa, 0, "StandardWindow", "")
        bb = win32gui.FindWindowEx(aaaa, b, "StandardWindow", "")
        self.input_dlg = win32gui.FindWindowEx(bb,0,"RichEditComponent", "")

        c = win32gui.FindWindowEx(b, 0, "PrivateWebCtrl", "")
        cc = win32gui.FindWindowEx(c,0,"Aef_WidgetWin_0","")
        self.msg_dlg = win32gui.FindWindowEx(cc,0,"Aef_RenderWidgetHostHWND", "Chrome Legacy Window")
        self.send_but = win32gui.FindWindowEx(bb,0,"StandardButton", "发送")

def save2troubleshoot(right,wrong,query,intent,slot,id):
    print("<CHANGED REPLY> Writing to troubleshoot.csv")
    df = pd.read_csv(r"troubleshoot.csv",encoding="gb18030",header=None)
    list_list=df.values.tolist()
    
    list_list.append([wrong,id,query,right,intent,slot])

    new_df = pd.DataFrame(data=list_list)
    new_df.to_csv(r"troubleshoot.csv",encoding="gb18030",index=0,header=0)

def send_message_QN(reply,cW,mode):
    #list of keybdEvents
    #https://blog.csdn.net/zhanglidn013/article/details/35988381

    # Paste text into the chatbox
    win32gui.SendMessage(cW.input_dlg, 0x000C, 0, reply)

    if mode == "":
        # AUTO SEND MODE
        win32gui.SendMessage(cW.send_but, 0xF5, 0, 0)
        print("Message Sent: {}".format(reply))

def setActiveScreen(target_window):
    win32gui.SetForegroundWindow(target_window)

    rect = win32gui.GetWindowRect(target_window)
    # Finds the top right position
    win32api.SetCursorPos((rect[2]-50,rect[1]+10))
    
    time.sleep(cmd_sleep)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN,0,0,0,0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,0,0,0,0)
    time.sleep(cmd_sleep)

def select_copy():
    #ctrl a
    win32api.keybd_event(17, 0, KEY_PRESS, 0)
    win32api.keybd_event(65, 0, KEY_PRESS, 0)
    time.sleep(cmd_sleep)
    #ctrl a release
    win32api.keybd_event(65, 0, KEY_LETGO, 0)
    win32api.keybd_event(17, 0, KEY_LETGO, 0)
    time.sleep(cmd_sleep)

    #ctrl c
    win32api.keybd_event(17, 0, KEY_PRESS, 0)
    win32api.keybd_event(67, 0, KEY_PRESS, 0)
    time.sleep(cmd_sleep)
    # ctrl c release 
    win32api.keybd_event(67, 0, KEY_LETGO, 0)
    win32api.keybd_event(17, 0, KEY_LETGO, 0)
    time.sleep(cmd_sleep)

def log_err():
    chatbot = os.getcwd()
    filename = os.path.join(chatbot,"errorlog",GLOBAL["today_date"] +".txt")
    f = open(filename, "w+")
    f.write(traceback.format_exc())

# Returns a reverse ordered list
def getRawText():
    rpt = 0
    rpt_limit = 10
    succeed = False
    while not succeed and rpt < rpt_limit:
        try:
            win32clipboard.OpenClipboard()
            succeed = True
        except Exception as e:
            print("OPEN CLIPBOARD EXCEPTION:",e,"Trying again...")
            log_err()
        rpt += 1

    time.sleep(clipboard_sleep)

    rpt = 0
    raw_text = ""
    while raw_text == "" and rpt < rpt_limit:
        try:
            raw_text = win32clipboard.GetClipboardData()
        except Exception as e:
            print("GET CLIPBOARD EXCEPTION:",e,"Trying again...")
            log_err()
        rpt += 1

    time.sleep(clipboard_sleep)

    try:
        win32clipboard.EmptyClipboard()
        succeed = True
    except Exception as e:
        print("EmptyClipboard EXCEPTION:",e)
        log_err()

    rpt = 0
    succeed = False
    while not succeed and rpt < rpt_limit + 10:
        try:
            win32clipboard.CloseClipboard()
            succeed = True
        except Exception as e:
            print("CLOSE CLIPBOARD EXCEPTION:",e,"Trying again...")
        rpt += 1

    raw_text_list = raw_text.splitlines()
    processed_text_list = []
    for sent in raw_text_list:
        sent = sent.strip()
        if sent != "" and sent != "以上为历史消息":
            processed_text_list.append(sent)
    processed_text_list.reverse()
    return processed_text_list

def check_if_edited(self_last_sent, query, custID):
    if not self_last_sent == GLOBAL["self_last_sent_msg"]:
        GLOBAL["self_last_sent_msg"] = self_last_sent

        last_bot_reply = GLOBAL.get("last_bot_reply","")
        print("<LAST SENT>",self_last_sent,"bot wanted to reply:",last_bot_reply)
        if not last_bot_reply == self_last_sent and not last_bot_reply == "":
            save2troubleshoot(str(self_last_sent), str(last_bot_reply), str(query), "intent", "slot info",str(custID))
    return

def collect_texts(collector, new):
    # Because reversed message order, new comes before old
    return  new + collector 

def get_customer_id(self_id,rawText):
    date_time_pattern = re.compile(r"\d*-\d*-\d* \d{2}:\d{2}:\d{2}")
    custid = ""
    for sent in rawText:
        if re.search(date_time_pattern,sent):
            if re.search(self_id,sent):
                # Contains Self ID
                continue
            else:
                custid = custid = re.sub(date_time_pattern,"",sent)
                break
    
    if custid == "": print("<GET CUSTOMER ID> Cannot find Customer ID")
    return custid


def processText(cW,rawText):
    date_time_pattern = re.compile(r"\d*-\d*-\d* \d{2}:\d{2}:\d{2}")
    recentText = rawText[:50]
    custid = ""
    self_last_sent = ""
    query = ""
    curr_text = ""
    querytime = ""
    print("RECENT TEXT", recentText[:10])
    for sent in recentText:
        if re.search(date_time_pattern,sent):
            # Name line
            if re.search(cW.userID,sent):
                # Self
                if self_last_sent == "":
                    self_last_sent = curr_text[:-2] # Remove the 已读/未读
            else:
                # Customer
                custid = re.sub(date_time_pattern,"",sent)
                if querytime == "": querytime = re.search(date_time_pattern,sent).group(0)
                query = collect_texts(query, curr_text)

            if len(query) > 0 and len(self_last_sent) > 0:
                break
            curr_text = ""
        else:
            # Text line
            curr_text = collect_texts(curr_text, sent) # Collect messages
    new_message_flag = not GLOBAL["last_query_time"] == querytime or not GLOBAL["last_query"] == query
    
    if new_message_flag:
        print("New Message deteced",querytime, query)
        GLOBAL["got_new_message"] = True
        GLOBAL["last_query_time"] = querytime
        GLOBAL["last_query"] = query
    else:
        GLOBAL["got_new_message"] = False

    check_if_edited(self_last_sent, query, custid)
    return query,custid

def mine_chat_text(cW):
    setActiveScreen(cW.msg_dlg)
    select_copy()
    return getRawText()

def check_new_message(cW):
    print('Checking for new messages...')
    rawText = mine_chat_text(cW)
    # print("*"*10+"Copied"+"*"*10)
    # print(rawText)
    query, cust_QN_ID = processText(cW,rawText)
    print("Customer ID: {} Query: {}".format(cust_QN_ID, query))
    return query, cust_QN_ID

# Returns nothing. Updates bot internal state.
def read_history(cW,bot):
    print('<HISTORY> Reading chat history')
    history = mine_chat_text(cW)
    cust_QN_ID = get_customer_id(cW.userID,history)
    mhist = get_only_messages(history,cW)
    bot.parse_transferred_messages(cust_QN_ID, mhist)
    return 

def get_only_messages(hist,cW):
    historyLimit = 500
    history = hist[:historyLimit]
    curr_text = ""
    out = []
    date_time_pattern = re.compile(r"\d*-\d*-\d* \d{2}:\d{2}:\d{2}")
    for sent in history:
        if re.search(date_time_pattern,sent):
            # Name line
            if not re.search(cW.userID,sent):
                # Customer ID
                # custid = re.sub(date_time_pattern,"",sent)
                # querytime = re.search(date_time_pattern,sent).group(0)
                out.append(curr_text)
            
            curr_text = ""
        else:
            # Text line
            curr_text = collect_texts(curr_text, sent) # Collect messages
    return out

#insert image path here for the series of place for the OCR to click on
def SeekNewCustomerChat(clickImage):
    print("Finding new chat...")

    Screen = jpype.JClass('org.sikuli.script.Screen')
    screen = Screen()

    try:
        screen.click(clickImage)
        return True
    except Exception:
        print("No new chat")
        log_err()
        return False

def select_chat_input_box(cW):
    if GLOBAL["mode"] == 0:
        print("Allowing user to enter input......")
        
        setActiveScreen(cW.input_dlg) # Select text input box
        
        # #ctrl + right
        # keybd_event(17, 0, KEY_PRESS, 0)
        # keybd_event(39, 0, KEY_PRESS, 0)
        # sleep(cmd_sleep)
        # #ctrl + right release
        # keybd_event(39, 0, KEY_LETGO, 0)
        # keybd_event(17, 0, KEY_LETGO, 0)

        while True:
            txtlen = win32gui.SendMessage(cW.input_dlg,win32con.WM_GETTEXTLENGTH,0,0)
            if txtlen == 0:
                time.sleep(GLOBAL["human_input_sleep"])
                txtlen = win32gui.SendMessage(cW.input_dlg,win32con.WM_GETTEXTLENGTH,0,0)
                if txtlen == 0:
                    print("Message Sent!!!")
                    break
            
    return

def main(cW,bot,SeekImagePath,mode,cycle_delay): 
    checks = 0
    while True:
        query, custID = check_new_message(cW)
        
        if GLOBAL["got_new_message"]:
            reply_template = bot.get_bot_reply(custID,query) # Gets a tuple of 3 things
            reply = reply_template[0]
            GLOBAL["last_bot_reply"] = reply
            if type(reply) == list:
                for r in reply:
                    send_message_QN(r,cW,mode)
            else:
                send_message_QN(reply,cW,mode)
                
        elif checks >= GLOBAL["new_chat_check_interval"]:
            newchat = SeekNewCustomerChat(SeekImagePath)
            checks = 0
            if newchat:
                read_history(cW,bot)
                GLOBAL["got_new_message"] = True
                continue

        checks += 1
        
        select_chat_input_box(cW) # This only does something if mode is "human control"

        for i in range(int(cycle_delay)):
            print("剩下{}秒".format(str(int(cycle_delay)-i))) 
            time.sleep(1)

if __name__ == "__main__":
    #SET MODE

    delay_time = input("Enter the delay time (in seconds) for each cycle to look for new message 投入延期(秒钟): ")
    #enter for testing, 1 for deployment
    mode = input("Enter the mode 投入模式: ")
    if mode == "": 
        GLOBAL["mode"] = 1 
    else:
        GLOBAL["mode"] = 0
        GLOBAL["human_input_sleep"] = float(input("Enter human reply delay 投入人工打回复延期(秒钟): "))

    #FIND WINDOW HANDLE
    try:
        regex = r".*(?= - 接待中心)"
        cW = QianNiuWindow()
        cW.find_window_regex(regex)
        cW.Maximize()
        cW.SetAsForegroundWindow()
        cW.find_handle()
        print(cW.userID,cW.msg_dlg,cW.input_dlg,cW.send_but)
    except:
        log_err()
    
    #START OCR & BOT
    projectDIR = os.getcwd()
    #set JAVA path
    defaultJVMpath = (r"C:\Program Files\Java\jdk-12.0.2\bin\server\jvm.dll")
    jarPath = "-Djava.class.path=" + os.path.join(projectDIR,r"sikuliX\sikulixapi.jar")
    SeekImagePath = os.path.join(projectDIR,r"sikuliX\A.PNG")

    print("Starting JVM...")
    jpype.startJVM(defaultJVMpath,'-ea',jarPath,convertStrings=False)
    jpype.java.lang.System.out.println("Started JVM!")

    bot = Chatbot()
    bot.start()
    
    #MAIN PROGRAMME LOOP
    print("Starting program....") 
    main(cW,bot,SeekImagePath,mode,delay_time)
