import cbsv
import re
import chatbot_utils as cu

SUPER_DEBUG = 0
DEBUG = 1

DEBUG = DEBUG or SUPER_DEBUG

# Have a message class? Or some sort of flag for messages. Indicate state-changing messages.
PREV_STATE_F = {"key":"299 PREV_STATE", "gated": False}
# PENDING_STATE_F = {"key":"PENDING_STATE", "gated": False}
SAME_STATE_F_OBJ = {"key":"same_state","gated":False}

# SIP = State Info Packet
# A packet that has info about state and has constructors for set states like go_back
class SIP:
    trans_state_flag = "transition_state"
    def __init__(self, state, cs = True):
        self.parse_state(state)
        self.state_change = cs
        self.backtrack = False
        self.go_back = False

    def parse_state(self, state):
        self.state_obj = state.copy() # Prevent unintended side effects. States are dicts
        self.state_key = self.state_obj["key"]
        self.gated_bool = self.state_obj.get("gated",False)
        self.transition_state = self.state_obj.get(self.trans_state_flag,False)
        self.state_slots = self.state_obj["req_info"] if self.gated_bool else []
        self.state_clears = self.state_obj.get("clear_info",[])
        self.pending_state = ""

    def set_actions(self, action, pending_act = None):
        self.action = action
        self.pending_act = pending_act

    def get_state_key(self):
        return self.state_key
    
    def get_state_obj(self):
        return self.state_obj

    def is_gated(self):
        return self.gated_bool

    # Returns a list of lists [name, type]
    def get_slots(self):
        return self.state_slots.copy()

    def get_reqs(self):
        return ReqGatekeeper.slots_to_reqs(self.state_slots)    

    def get_clears(self):
        return self.state_clears.copy()

    @classmethod
    def same_state(cls):
        obj = cls(SAME_STATE_F_OBJ, cs=False)
        return obj
    
    @classmethod
    def exit_pocket(cls):
        # TODO this
        obj = cls(PREV_STATE_F, cs=False)
        return obj

    def is_same_state(self):
        return not self.state_change

    def is_trans_state(self):
        return self.transition_state

    def is_go_back(self):
        return self.go_back == True

    def toString(self):
        return ("State key",self.state_key,"cs",self.state_change, "slots",self.state_slots)

# A vehicle to house SIP and intent.
class Understanding:
    def __init__(self, original_intent_obj, intent_obj, sip):
        self.og_intent = original_intent_obj
        self.intent = intent_obj
        self.sip = sip
        self.details = {}

    def get_intent(self):
        return self.intent

    def get_og_intent(self):
        return self.og_intent

    def get_sip(self):
        return self.sip
    
    def get_sip_slots(self):
        return self.sip.get_slots()

    def printout(self):
        print("UNDERSTANDING OBJ PRINTOUT Intent: ", self.intent, " SIP: ", self.sip.toString())

class ReqGatekeeper:
    def __init__(self, conds, default_slot_vals):
        self.requirements = []
        self.slots = []
        self.gate_closed = False
        self.conds = conds
        self.default_slot_vals = default_slot_vals
        self.def_slot_flag = "DEFAULT_SV"

    def open_gate(self):
        self.gate_closed = False
        self.slots = []
        self.requirements = []

    def close_gate(self):
        self.gate_closed = True

    def get_slots(self):        
        return self.slots.copy()

    def _get_slots_name_list(self, sl):
        return list(map(lambda x: x[0],sl))

    def get_slot_names(self):
        return self._get_slots_name_list(self.get_slots())

    def get_default_slots(self):
        slots = self.get_slots()
        out = list(filter(lambda x: x[1] == self.def_slot_flag,slots))
        return out

    def get_def_slot_names(self):
        return self._get_slots_name_list(self.get_default_slots())

    def is_gated(self):
        return self.gate_closed

    def _add_cond_reqs(self, info):
        # Additional reqs
        for detail, conditions in self.conds.items():
            fetch = cu.dive_for_values([detail,],info,DEBUG=1)
            if len(fetch) > 0:
                for c in conditions:
                    val, slots_list = c
                    fetched = list(fetch.values())
                    if SUPER_DEBUG: print("<CONDITIONAL REQS>f,fval,val",fetch, fetched,val) 
                    if fetched[0] == val:
                        for slot in slots_list:
                            if not slot[0] in self.get_slot_names():
                                if DEBUG: print("<CONDITIONAL REQS> Update COND slots: ", slot)
                                self.slots.append(slot)
                        break

    @classmethod
    def slots_to_reqs(cls, slots):
        def getname(s):
            return s[0]
        reqlist = []
        for slot in slots.copy():
            reqlist.append(getname(slot))
        if DEBUG: print("<slots_to_reqs> return:", reqlist)
        return reqlist  

    def get_requirements(self):
        return self.requirements.copy()

    def scan_SIP(self, sip):
        so = sip.get_state_obj()
        return self.scan_state_obj(so)

    def scan_state_obj(self, state_obj):
        if "gated" not in state_obj:
            return

        slots = state_obj.get('req_info',[])
        if not state_obj["gated"] or len(slots) < 1:
            return
       
        self.close_gate()
        self.slots = slots
        if DEBUG: print("<SCAN STATE OBJ> slots:",slots)
        self.requirements = ReqGatekeeper.slots_to_reqs(self.slots)      

    # If pass, returns True, (Pending state)
    # If fail, returns False, (Next state)
    def try_gate(self, info):
        def is_passed(us):
            return (len(us) == 0)

        if not self.gate_closed:
            # If the gate is open
            passed = True
            unfilled_slots = []
            info_topup = {}

        else:
            self._add_cond_reqs(info)
            unfilled_slots = self.get_slots()

            if SUPER_DEBUG: print("<TRY GATE> Trying with info:",info, "required:",self.get_requirements())
            # for catgry in list(info.keys()):
            for s in unfilled_slots.copy():
                detail = s[0]
                if detail in info:
                    unfilled_slots.remove(s)
            
            # Fill slots with default values if needed
            unfilled_slots, info_topup = self.assign_default_values(unfilled_slots)

            if DEBUG: print("<TRY GATE> Unfilled_slots:",unfilled_slots)
            if len(unfilled_slots) == 0:
                self.open_gate()

            passed = is_passed(unfilled_slots)
        
        return (passed, unfilled_slots, info_topup)

    def assign_default_values(self, unfilled):
        def is_default(s):
            return s[1] == self.def_slot_flag

        post_unfilled = unfilled.copy()
        info_topup = {}
        for slot in unfilled.copy():
            if SUPER_DEBUG: print("<DEFAULT VALS> curr slot",slot,"is def:", is_default(slot))
            if is_default(slot):
                slotname, slot_type_UNUSED = slot
                if slotname in self.default_slot_vals:
                    val = self.default_slot_vals[slotname]
                    info_topup[slotname] = val
                    post_unfilled.remove(slot)
                    if DEBUG: print("<DEFAULT VALS> {} assigned default value: {}".format(slotname, val))
        if DEBUG: print("<DEFAULT VALS> post top up", info_topup)
        return (post_unfilled, info_topup)

class Humanizer():
    def __init__(self,human_dict):
        self.hd = human_dict.items()
    
    def humanify(self, msg, info):
        def add_humanlike_text(iv, d, in_msg):
            specific_dict = d[iv]
            pos = specific_dict["location"]
            txt = specific_dict["text"]
            if pos == "START":
                return txt + in_msg
            elif pos == "END":
                return in_msg + txt
            return in_msg

        human_msg = msg
        ctx_key = InfoParser.CTX_SLOT_KEY()
        ctx_info = info.get(ctx_key,{})
        for key, dic in self.hd:
            inf_val = ctx_info.get(key,"")
            if inf_val in dic:
                human_msg = add_humanlike_text(inf_val, dic, human_msg)
            
        return human_msg
        

class Policy():
    def __init__(self, g_intents, s_intents = []):
        # self.state_name = state_name
        self.g_intents = g_intents
        self.s_intents = s_intents

    def get_g_intents(self):
        return self.g_intents

    def get_s_intents(self):
        return self.s_intents

    def get_intents(self):
        return [self.s_intents, self.g_intents]

CITIES = cbsv.CHINA_CITIES()
class Customer:
    def __init__(self, userID, accounts = -1, issues = -1):
        self.userID = userID
        self.city = ""
        self.start_date = ""
        if isinstance(issues,int): 
            self.accounts = [] 
        else: 
            self.accounts = accounts
        if isinstance(issues,int):
            self.issues_list = []
        else:
            self.issues_list = issues
        
    def record_city(self,city):
        assert city in CITIES
        self.city = city

    def add_issue(self, issue):
        self.issues_list.append(issue)
        # Check for duplicates?

    def get_issues(self):
        return self.issues_list

    def get_accounts(self):
        return self.accounts

# Globally accessed object. Singleton but not really cuz it needs to be initalized
class InfoVault():
    def __init__(self, json_data):
        self.vault_info = json_data["vault_info"]
        self.general_info = self.vault_info["general_info"]
        self.lookup_info = self.vault_info["lookup_info"]
        self.slot_list = list(self.lookup_info.keys())
    
    # Modifies the dict directly
    def add_vault_info(self, chatinf):
        self._add_lookup_info(chatinf)
        self._add_general_info(chatinf)
        return

    def _add_lookup_info(self, chatinfo):
        def add_entry(s):
            chatval = chatinfo[s] # Chat provided value
            v_subdict = self.lookup_info[s]
            t_key = v_subdict["writeto"]
            if chatval in v_subdict:
                v_info = v_subdict[chatval]
                entry = {t_key:v_info}
                # if DEBUG: print("<ADD VAULT INFO> entry",entry,t_key,":",v_info)
                chatinfo.update(entry)
        # if DEBUG: print("<ADD VAULT INFO> list:",self.slot_list)
        for s in self.slot_list:
            if s in chatinfo:
                add_entry(s)
                
        return

    def _add_general_info(self, ci):
        gen_info = {"general_info":self.general_info}
        ci.update(gen_info)
        return
        
# Takes in a message and returns some info (if any)
# Note: thing about re.search is that only the first match is pulled.
class InfoParser():
    def __init__(self, json_dict):
        self.digits = cbsv.DIGITS()
        self.ctxsk = self.CTX_SLOT_KEY()
        self.regexDB = {}
        self.perm_slots = json_dict["permanent_slots"]
        self.ctx_slots = json_dict["contextual_slots"]
        slots = json_dict["slots"]
        self._build_slots_DB(slots)

    @classmethod
    def CTX_SLOT_KEY(cls):
        return "ctx_slots"

    def _build_slots_DB(self, jdata):
        for catkey in list(jdata.keys()):
            self.regexDB[catkey] = {}
            category = jdata[catkey]
            for value in list(category.keys()):
                termlist = category[value]
                regexlist = self.list_to_regexList(termlist)
                self.regexDB[catkey][value] = regexlist


    # Updates dict directly
    def _match_slot(self, text, slot, d, PDB = True):
        slotname, catgry = slot
        value = self.get_category_value(text, catgry, PDB)
        if len(value) > 0:
            if SUPER_DEBUG: print("<MATCH SLOT> Found a {} for {} Value: {}".format(catgry, slotname,value))
            entry = {slotname: value}
            d.update(entry)

    def _parse_function(self, text, d, slots, PDB = True):
        for s in slots:
            self._match_slot(text, s, d, PDB)
        
    # Searches in permanent aka default slots
    def _default_parse(self, text, d, PDB = True):
        self._parse_function(text, d, self.perm_slots, PDB)
        return

    # Searches in contextual slots
    def _contextual_parse(self, text, d):
        if not self.ctxsk in d:
            d[self.ctxsk] = {}
        if DEBUG: print("CTX",self.ctx_slots)
        self._parse_function(text,d[self.ctxsk],self.ctx_slots)
        return


    def _no_match_val(self, catDB):
        keyword = "NO_MATCH"
        defval = ""
        if keyword in catDB:
            defval = catDB[keyword]
        
        return defval

    def _intent_blanket_slotfill(self, intent, slots, d):
        int_slotpairs = intent.get("slotfills",[])
        out = {}
        for fillslotname, slottype in slots:
            if slottype in int_slotpairs:
                filval = int_slotpairs[slottype]
                out[fillslotname] = filval
        d.update(out)
        return

    # Get the value in the text related to the specified category
    # Enumerated by dictionary key
    # Returns a pure value
    def get_category_value(self, text, category, PDB = True):
        if not category in self.regexDB:
            if PDB and DEBUG: print("<GET CAT VAL> No such category:{}".format(category))
            return ""
        catDB = self.regexDB[category]
        value = self._no_match_val(catDB)
        found = False
        vals = list(catDB.keys())
        for v in vals:
            reDB = catDB[v]
            m = re.search(reDB, text)
            if m:
                if PDB and SUPER_DEBUG: print("<GET CAT VAL> Matched {} value:{} at {}".format(category,v,m))
                if found:
                    if PDB: print("<GET CAT VAL> Double value. Prev:", value, ", Current:",v)
                # token = m.group(0)
                value = v
                found = True
                # if DEBUG: print("<PARSER> Found a ", category, ":", v)
        
        return value

    ### MAIN FUNCTION ### 
    # Returns a dict of primary lookup_info including zones.
    def parse(self, text, slots, intent):
        if not isinstance(intent, dict):
            return {}
        out = {}
        # Intent slotfill
        self._intent_blanket_slotfill(intent, slots, out)
        # State Slot parse
        self._parse_function(text, out, slots)
        # Permanent slot parse (overwrites existing slots)
        self._default_parse(text,out)
        # Contextual parse
        self._contextual_parse(text, out)
        # if DEBUG: print("<PARSE> Final details:",out)
        return out

    def parse_chat_history(self, history):
        out = {}
        # Permanent slot parse (overwrites existing slots)
        for msg in history:
            self._default_parse(msg, out, PDB = False)
        if DEBUG: print("<PARSE HISTORY> History info:",out)
        return out 

    # Converts a python array to a string delimited by the '|' character
    def list_to_regexList(self, lst):
        re_list = ""
        for e in lst:
            re_list = re_list + e + "|"
        re_list = re_list[:-1] # Remove last char "|"
        return re_list

    def parse_date(self, text):
        # Returns a "" if not found
        def date_re_search(keyword):
            result = ""
            # "[^ ]+(?=日)"
            search_terms = self.digits + "+(?=" + keyword + ")"
            m = re.search(search_terms,text)
            if m:
                result = m.group(0)
            return result
        
        day = date_re_search("日")
        mth = date_re_search("月")
        yr = date_re_search("年")

        out = (day, mth, yr)
        return out

    @classmethod
    def cn_to_integer(self, msg):
        SHI = "十"
        zw_num = ['零','一','二','三','四','五','六','七','八','九']
        def get_decimal(haoma):
            return str(zw_num.index(haoma))
        output = msg
        j = 0
        for i in range(len(msg)):
            if msg[i] == SHI:
                # Tens digit
                rest = output[j+1:] if j+1 < len(output) else ""
                output = output[:j] + "0" + rest
                
                if not msg[i-1] in zw_num:
                    # If standalone
                    rest = output[j:]
                    output = output[:j] + "1" + rest
                    j+=1
                
                if i+1 < len(msg):
                    # If have ones digit, replace zerp with ones digit
                    if msg[i+1] in zw_num:
                        rest = output[j+1:] if j+1 < len(output) else ""
                        output = output[:j] + rest
            j += 1
        # Mass replace digits
        for haoma in zw_num:
            output = output.replace(haoma, get_decimal(haoma))

        return output

if __name__ == "__main__":
    print("Number Converter On!")
    while 1:
        test = input()
        print("converted:",InfoParser.cn_to_integer(test))