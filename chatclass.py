# All Chat related Classes

import re
import random
import cbsv
import string
import os
import chatbot_be
from datetime import datetime
from chatbot_supp import *
from chatbot_utils import dive_for_values

DEBUG = 1

# A conversation thread manager using stack and dict
class StateThreader():
    def __init__(self, default_state):
        self.default_state = default_state
        self.threadIDstack = [] # A stack of threadIDs
        self.threadmap = {}
        self.state_changed = True
        self.spawn_thread(default_state, threadID = "BASE") # Spawn base thread

    def get_curr_threadID(self):
        return self.threadIDstack[-1]

    def get_curr_thread(self):
        key = self.get_curr_threadID()
        thrd = self.threadmap[key]
        return thrd

    def _get_threadID(self, state):
        return state["thread"]

    # UNUSED intentionally. KIV.
    def state_never_change(self):
        return not self.state_changed

    def _thread_same_state(self, nstate):
        # print("new vs old", nstate, self.get_curr_thread_state())
        if DEBUG: print("StateThreader samestate:",self.get_curr_thread()._is_same_state(nstate))
        return self.get_curr_thread()._is_same_state(nstate)

    def _thread_same_id(self, tid):
        tid == self.get_curr_threadID()
    
    def spawn_thread(self, start_state = -1, threadID = "DEFAULT"):
        if isinstance(start_state, int):
            raise Exception("Tried to spawn thread but no start state provided")
        newthread = ConvoThread(start_state)
        self.threadIDstack.append(threadID)
        self.threadmap[threadID] = newthread
    
    def get_curr_thread_state(self):
        state = self.get_curr_thread().get_curr_state()
        if isinstance(state, SIP):
            raise Exception("SIP DETECTED{}".format(state.toString()))
        return state

    def kill_curr_thread(self):
        if len(self.threadIDstack) > 1:
            deadthreadID = self.threadIDstack.pop(-1)
            self.threadmap.pop(deadthreadID)

            new_headID = self.threadIDstack[-1]
            if DEBUG : print("KILLING THREAD:",deadthreadID,"NEW HEAD:",new_headID)

    def switch_thread_to(self, threadID):
        # Push to front of stack
        self.threadIDstack.remove(threadID)
        self.threadIDstack.append(threadID)
        return

    def update_thread_state(self, new_state_obj):
        def _is_terminal_state(state):
            tskey = "terminal_state"
            if tskey in state:
                return state["terminal_state"]
            else:
                return False

        def need_switch_thread(threadID):
            return not (threadID == "NONE" or self._thread_same_id(threadID))

        ns_threadID = self._get_threadID(new_state_obj)
        UPDATE_STATE_BOOL = True
        curr_state = self.get_curr_thread_state()

        if _is_terminal_state(curr_state):
            UPDATE_STATE_BOOL = not self._thread_same_state(new_state_obj)
            self.kill_curr_thread()
        
        if need_switch_thread(ns_threadID):
            if ns_threadID in self.threadmap:
                self.switch_thread_to(ns_threadID)
            else:
                self.spawn_thread(new_state_obj, ns_threadID)
        
        if UPDATE_STATE_BOOL:
            self.get_curr_thread().update_state(new_state_obj)

        if DEBUG: print("<STATETHREADER>Statestack", self.threadIDstack)

        return UPDATE_STATE_BOOL

    # Assigns the pending state to the current thread
    def set_thread_pending(self, hs, ps):
        self.get_curr_thread().set_pending_state(hs,ps)

    # If has pending, returns pending
    # If nothing pending, returns given_next_state
    def move_forward(self, given_next_state):
        if self.get_curr_thread().has_pending_state():
            if DEBUG: print("Unlocking...")
            self.get_curr_thread().unlock_pending_state()
            self.state_changed = True
        else:
            self.state_changed = self.update_thread_state(given_next_state)
        return self.get_curr_thread_state()

# A conversation thread
# Tracks state
class ConvoThread:
    def __init__(self, initial_state):
        self.curr_state = initial_state
        self.pend_state = None
        self.state_history = [self.curr_state]
        self.required_info = []

    def _is_same_state(self, ns):
        return ns == self.curr_state

    def update_state(self, new_state):
        notsamestate = not self._is_same_state(new_state)
        if notsamestate:
            self.state_history.append(self.curr_state)
            self.curr_state = new_state
        return notsamestate

    def get_prev_state(self):
        return self.state_history[-1]

    def get_curr_state(self):
        return self.curr_state

    def has_pending_state(self):
        return not self.pend_state == None
    
    def get_pending_state(self):
        return self.pend_state
    
    def _clear_pending(self):
        self.pend_state = None

    def set_pending_state(self, holdstate, pstate):
        if self.has_pending_state():
            if DEBUG: print("<ConvoThread> Existing pend state:{} new:{}".format(self.get_pending_state(), pstate))
            return
        if DEBUG: print("<ConvoThread> Setting pending state:",pstate)
        self.pend_state = pstate
        self.update_state(holdstate)
        return

    def unlock_pending_state(self):
        if not self.has_pending_state():
            # raise Exception("No pending to unlock!")
            return
        self.update_state(self.get_pending_state())
        self._clear_pending()
        return

# Keeps track of zones like city
class ZoneTracker:
    def __init__(self):
        self.zones = {}

    def _add_zone(self, z, val):
        # if z in self.zones:
        #     if DEBUG: print("<ADD ZONE> Existing zone {}:{}. Did not write {}.".format(z,self.zones[z],val))
        #     return
        self.zones[z] = val

    # Fetches info from the dm
    def update_zones_from_dm(self, dm):
        all_info = dm.fetch_info()
        zkey = "zones"
        if zkey in all_info:
            zone_dic = all_info[zkey]
            for z, val in zone_dic.items():
                self._add_zone(z, val)
        return

    def get_zones(self):
        return self.zones.copy()

    def get_zone_val(self, z):
        if not z in self.zones:
            return None
        return self.zones[z]

# Coordinates everything about a chat
class ChatManager:
    def __init__(self, chat, iparser, pkeeper, replygen, dmanager, gkeeper):
        # Internal properties
        self.chat = chat
        self.chatID = self.chat.getID()
        self.samestateflag = False

        # Helper classes
        self.iparser = iparser
        self.pkeeper = pkeeper
        self.replygen = replygen
        self.dmanager = dmanager.clone(self.chatID)
        self.gatekeeper = gkeeper
        self.statethreader = StateThreader(pkeeper.GET_INITIAL_STATE())
        self.ztracker = ZoneTracker()
        self.INFORM_INT = pkeeper.GET_INFORM_INTENT() # TODO Not very good OOP


    def _get_curr_state(self):
        return self.statethreader.get_curr_thread_state()

    def _get_csk(self):
        return cbsv.getstatekey(self._get_curr_state())

    def _get_zones(self):
        return self.ztracker.get_zones()
    
    ############### PRIMARY METHOD ###############
    # Takes in a message, returns (text reply, intent breakdown, current info)
    def respond_to_message(self, msg):
        print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~&") # For clarity in terminal
     
        repeat = True
        rc = 0

        # IDK why this arrangement works but it does. Needs investigation/clarity.
        # I think its because the SIP is changed to same_state once repeat is triggered.
        # Thus, the only change of state is due to crossroading. Also, you don't get stuck at a crossroad because of SAME_STATE cycling.

        while repeat and rc < 5:
            # Parse the message and get an understanding
            full_uds, bd = self._parse_message_overall(msg)
            if rc == 0:
                sip = full_uds.get_sip()

            # Digest and internalize the new info
            repeat, pg = self.react_to_sip(sip)

            # Request a reply text
            intent = full_uds.get_intent()

            if DEBUG: print("<RTM> Repeats", rc, "Pass gate:",pg)
            # if repeat:
            #     sip = SIP.same_state()

            rc += 1
       
        reply, calc_topup = self._fetch_reply(intent)
        self.push_detail_to_dm(calc_topup)

        curr_info = self._get_current_info()

        # Records message logs
        self._record_messages_in_chat(msg,reply)
        return (reply, bd, curr_info)

    # Takes in message text, returns (understanding object, nlp breakdown)
    def _parse_message_overall(self,msg):
        # Inital understanding
        uds, bd, nums = self._policykeeper_parse(msg)
        if DEBUG: print("Initial UDS:")
        if DEBUG: uds.printout()
        self.gatekeeper.scan_SIP(uds.get_sip()) # THIS IS USEFUL for pre-filling slots

        # Mine message details. 
        # This is after gatekeep because gatekeep sets the slots.
        og_int = uds.get_og_intent()
        self._parse_message_details(msg, nums,og_int)

        return uds, bd
    
    # Process, gatekeep then internalize changes
    # Results in change in chat details and change in state
    # Returns boolean indicating whether or not the state was overwritten.
    def react_to_sip(self, sip):
        
        if sip.is_same_state():
            if DEBUG: print("<REACTION> SAME STATE FLAGGED")
            self.samestateflag = True
            stateobj = self._get_curr_state()
        else:
            self.samestateflag = False
            stateobj = sip.get_state_obj()
        if DEBUG: print("<REACTION> Curr state", self._get_curr_state()["key"], "Nxt stateobj", stateobj["key"])
        # Check if current target state is in a zone_policy crossroad 
        ow_flag, stateobj = self._zone_policy_overwrite(stateobj)

        # Gatekeeper gets the requirements from the state
        self._get_slots_from_state(stateobj)
        # Gatekeeper tries the gate
        pass_gate = self._advance_to_new_state(stateobj)

        return (ow_flag, pass_gate)

    def _move_forward_state(self, state):
        self.statethreader.move_forward(state)

    def _get_slots_from_state(self, stateobj):
        self.gatekeeper.scan_state_obj(stateobj)

    # CHANGES STATE
    # Updates state according to outcome
    def _advance_to_new_state(self, nextstate):
        def _make_info_sip(req_info):
            con_sip = self.pkeeper.make_info_req_sip(req_info)
            return con_sip

        def _set_thread_pending(hs, ps):
            self.statethreader.set_thread_pending(hs, ps)
        
        curr_info = self._get_current_info()
        print("Current info:",curr_info)
        passed, req_slots, info_topup = self.gatekeeper.try_gate(curr_info)

        self.push_detail_to_dm(info_topup, ow=False) # Detail update. No Overwrite

        if DEBUG: print("Gate passed:",passed)

        if passed:
            self._move_forward_state(nextstate)
        else:
            # Update DetailManager
            self.push_req_slots_to_dm(req_slots)

            # Didnt pass gate
            constructed_sip = _make_info_sip(req_slots)
            infostate = constructed_sip.get_state_obj()
            _set_thread_pending(infostate, nextstate)

        return passed

    # Overwrites state if in zone policy
    def _zone_policy_overwrite(self, og_nxt_state):
        csk = og_nxt_state["key"]
        zones = self._get_zones()
        overwrite_flag, ow_state = self.pkeeper.zone_policy_overwrite(csk,zones)
        if DEBUG: print("<ZONE POLICY>",overwrite_flag,ow_state)
        if overwrite_flag:
            return (True, ow_state)
        else:
            return (False, og_nxt_state)

    def push_req_slots_to_dm(self, required_slots):
        if len(required_slots) > 0:
            required_info = list(map(lambda x: x[0],required_slots)) # First element
            print("pushslotstodm Reqinfo",required_info)
            info_entry = {"requested_info": required_info}
            self.push_detail_to_dm(info_entry)
        return

    ### Ask Helpers
    # Ask replygen for a reply
    def _fetch_reply(self,intent):
        information = self._get_current_info()
        curr_state = self._get_curr_state()
        if DEBUG: print("<Fetch Reply> Current State",curr_state)
        # samestateflag = self.statethreader.state_never_change()
        samestateflag = self.samestateflag
        # print("curr_state", curr_state['key'], "samestate",samestateflag)
        return self.replygen.get_reply(curr_state, intent, samestateflag, information)

    # Asks dmanager for info
    def _get_current_info(self):
        return self.dmanager.fetch_info()

     # Gets the next state according to policy
    def _policykeeper_parse(self, msg):
        csk = self._get_csk()
        return self.pkeeper.get_understanding(msg, csk)

    # Asks iparser to parse the message
    def _parse_message_details(self, msg, nums, intent):
        slots = self.gatekeeper.get_slots() # Only look out for what is needed
        details = self.iparser.parse(msg, slots, intent)

        # Append parsed number to details
        bignum = max(nums) if len(nums) > 0 else 0
        if bignum > 0:
            details["given_amount"] = bignum ## TODO: Work in PROGRESS. Gets the biggest number from the list
        
        self.push_detail_to_dm(details)
        return

    ### Detail logging
    def push_detail_to_dm(self, d, ow=1):
        self.dmanager.log_detail(d, OVERWRITE=1)
        self.ztracker.update_zones_from_dm(self.dmanager)
        return 

    ### Chat logging
    def _record_messages_in_chat(self,recv, sent):
        self.chat.record_messages(recv,sent)
        return
    
    def backup_chat(self):
        self.chat.record_to_database()
        return

# Keeps policies
# Also deciphers messages
class PolicyKeeper:
    def __init__(self, policy_rules, zone_policies, intent_dict, state_lib,pp):
        self.POLICY_RULES = policy_rules
        self.ZONE_POLICIES = zone_policies
        self.INTENT_DICT = intent_dict
        self.STATE_DICT = state_lib
        self.predictor = pp

    def GET_INITIAL_STATE(self):
        initstate = self.STATE_DICT['init']
        return initstate

    def GET_INFORM_INTENT(self):
        initstate = self.INTENT_DICT['inform']
        return initstate

    def make_info_req_sip(self, req_info):
        def set_info(state, info):
            # Alters the state
            assert state["gated"]
            state["req_info"] = req_info

        if len(req_info) < 1:
            raise Exception("Tried to construct reqinfo SIP but required info is empty!")

        ig_state = self.STATE_DICT["TMP_recv_info"].copy()
        set_info(ig_state, req_info)
        out = SIP(ig_state, cs=False)
        return out

    def _NLP_predict(self,msg):
        pack = self.predictor.predict(msg)
        intent = pack["prediction"]
        breakdown = pack["breakdown"]
        nums = pack["numbers"]
        return intent, breakdown, nums

    # MAIN METHOD
    # Returns an understanding and NLP breakdown
    def get_understanding(self, msg, curr_state):
        # Call NLP Model predict
        intent, breakdown, nums = self._NLP_predict(msg)
        print("NLP intent:",intent)
        # Check intent against background info
        uds = self.intent_to_next_state(curr_state, intent)
        return uds, breakdown, nums

    def _create_state_obj(self, sk):
        if not sk in self.STATE_DICT:
            print("<PolicyKeeper> Illegal state:",sk)
            return SIP.same_state().get_state_key() # Bad.
        state_obj = self.STATE_DICT[sk]
        return state_obj

    # METHOD FOR NLP
    def intent_to_next_state(self, csk, intent):
        if intent in self.INTENT_DICT:
            intent_obj = self.INTENT_DICT[intent]
        else:
            intent_obj = False

        policy = self.POLICY_RULES[csk]
        default_null_int = self.INTENT_DICT["no_intent"]
        uds = Understanding(intent_obj, default_null_int,SIP.same_state())
        for intent_lst in policy.get_intents():
            print("intent_list",list(map(lambda x: x[0],intent_lst)))
            for pair in intent_lst:
                c_int, next_sip = pair
                if intent == c_int:
                    print("MATCH",intent)
                    uds = Understanding(intent_obj, intent_obj, next_sip)
                    return uds
        return uds

    def zone_policy_overwrite(self, csk, chat_zones):
        def check_zonepolicies(state_key):
            return state_key in self.ZONE_POLICIES

        print("<ZPO> csk",csk)
        # Zone policy
        if check_zonepolicies(csk):
            z, paths = self.ZONE_POLICIES[csk]
        
            if z in chat_zones:
                z_val = chat_zones[z]
                if z_val in paths:
                    target = paths[z_val]
                else:
                    target = paths["DEFAULT"]
                next_sip = self._create_state_obj(target)
                if DEBUG: print("<ZP OVERWRITE> new SIP:",next_sip)
                return (True, next_sip)

        return (False, "")

    # OLD METHOD USING SEARCH. NOT USED
    # def decipher_message(self,curr_state,msg):
    #     def get_intent_matchdb(intent):
    #         if not "matchdb" in intent:
    #             raise Exception("intent missing matchdb, {}".format(intent))
    #         return intent["matchdb"]

    #     # Returns an Understanding minus details
    #     def uds_from_policies(state, msg):
    #         if DEBUG: print("uds from state:",state)
    #         policy = self.POLICY_RULES[state]
    #         # print("policy list intents", policy.get_intents())
    #         for intent_lst in policy.get_intents():
    #             for pair in intent_lst:
    #                 intent, next_sip = pair
    #                 assert isinstance(next_sip, SIP)
    #                 keyword_db = get_intent_matchdb(intent)
    #                 if cbsv.check_input_against_db(msg, keyword_db):
    #                     return Understanding(intent, next_sip)
    #         return Understanding.make_null()
        
    #     uds = uds_from_policies(curr_state,msg)

    #     return uds

# MANAGES DETAILS (previously held by Chat)
# TODO: Differentiate between contextual chat info and user info?
class DetailManager:
    def __init__(self, info_vault,secondary_slots,zonelist):
        self.vault = info_vault
        self.inital_dict = {}
        self.inital_dict["zones"] = {}
        self.chat_prov_info = self.inital_dict
        self.dbrunner = {"dummy"}
        self.dbrunnerset = False
        self.chatID = "PLACEHOLDER_USERID"
        self.zonelist = zonelist
        self.second_slots = secondary_slots

    def set_runner(self, runner):
        self.dbrunner = runner
        self.dbrunnerset = True

    def _set_chatID(self, chatID):
        self.chatID = chatID
        # prev_info = self.dbrunner.fetch_user_info(chatID)
        # self.chat_prov_info.update(prev_info)

    # Adds a zone dict to the supplied dict
    # E.g. "zones":{"city":"shanghai"}
    def _update_zones(self):
        d = self.chat_prov_info
        zones_d = {}
        for zone in self.zonelist:
            if zone in d:
                zones_d[zone] = d[zone]

        if not zones_d == {}: 
            d["zones"].update(zones_d)

    def log_detail(self, new_info, OVERWRITE = 1, DEBUG = 0):
        if DEBUG: print("Logging", new_info)
        for d in new_info:
            deet = new_info[d]
            # Check to make sure its not empty
            if not deet == "":
                if d in self.chat_prov_info and not OVERWRITE:
                    continue
                else:
                    self.chat_prov_info[d] = new_info[d]
                
        self._add_secondary_slots()

        self._update_server_state_info()

        self.write_info_to_db()

        self._update_zones()
        return

    # Info without vault
    def get_user_info(self):
        not_user_info = ["requested_info", "paile","拍了"] #TODO find a proper way to store this info in JSON
        dic = self.chat_prov_info.copy()
        for i in not_user_info:
            if i in dic: 
                dic.pop(i)
        return dic
    
    def _update_server_state_info(self):
        dt_now = datetime.now()
        server_info = {}
        server_info["state_curr_hour"] = dt_now.hour
        server_info["state_month"] = dt_now.month
        server_info["state_curr_day"] = dt_now.day
        self.chat_prov_info.update(server_info)
        return

    def _add_secondary_slots(self):
        
        curr_info = self.fetch_info()
        ss_default_flag = "DEFAULT"

        def tree_search(tree, info):
            slot, sub_dict = list(tree.items())[0]
            while slot in info:
                slot_val = str(info[slot]) # To convert ints to strings. I.e. for hours
                if slot_val in sub_dict:
                    ss_branch = sub_dict[slot_val]
                    if isinstance(ss_branch, dict):
                        slot, sub_dict = list(ss_branch.items())[0]
                    else:
                        return (True, ss_branch)
                else:
                    if DEBUG: print("<SECONDARY SLOT> Val not found:", slot_val)
                    break
            return (False, "")

        entries = {}
        for secondslot in self.second_slots:
            target = secondslot["writeto"]
            tree = secondslot["search_tree"]

            f, val = tree_search(tree, curr_info)
            if f: 
                entries[target] = val
            elif ss_default_flag in secondslot:
                 entries[target] = secondslot[ss_default_flag]
        
        self.chat_prov_info.update(entries)
        return 

    # Called to get chat info + vault info
    def fetch_info(self):
        out = {}
        out.update(self.chat_prov_info)
        self.vault.add_vault_info(out)
        return out

    # This is called during the creation of a new chat
    def clone(self, chatID):   
        if not self.dbrunnerset:
            raise Exception("DatabaseRunner not initalized for DetailManager!")
        clonetrooper = DetailManager(self.vault, self.second_slots, self.zonelist)
        clonetrooper._set_chatID(chatID)
        clonetrooper.set_runner(self.dbrunner)
        prev_info = self.dbrunner.fetch_user_info(chatID)
        clonetrooper.log_detail(prev_info)
        return clonetrooper

    def write_info_to_db(self):
        if not self.dbrunnerset:
            raise Exception("DatabaseRunner not initalized for DetailManager!")
        chatid = self.chatID
        self.dbrunner.write_to_db(chatid, self.get_user_info())

# Generates reply text based on current state info
class ReplyGenerator:
    def __init__(self, formattingDB, humanizer, def_confused):
        self.formatDB = formattingDB
        self.formatter = string.Formatter()
        self.humanizer = humanizer
        self.hflag = True
        self.default_confused = def_confused
        
    # OVERALL METHOD
    def get_reply(self, curr_state, intent, secondslot, info = -1):
        rdb = self.getreplydb(intent, curr_state, secondslot)
        infoplus, info_topup = self._enhance_info(curr_state, info)
        reply = self.generate_reply_message(rdb, infoplus)
        return (reply, info_topup)

    # Formats txts and calculates
    # Big function
    def _enhance_info(self,curr_state,info):
        enhanced = info.copy()
        if DEBUG: print("initial info", enhanced)
        rep_ext = {}
        l_calc_ext = {}
        topup = {}

        cskey = curr_state["key"]
        state_calcs = False

        formatDB = self.formatDB["msg_formats"]
        calcDB = self.formatDB["calcs"]

        def add_enh(key, value, ext_dict,subdict_name, pv = False, overwrite = False):
            if DEBUG: print("Enhancing!{}:{}".format(key,value))

            if key in ext_dict and not overwrite:
                ext_dict[key] = ext_dict[key] + value
            else:
                ext_dict[key] = value
            
      
            # Dict of info to be returned and written into main info
            if pv:
                topup[key] = value
                enhanced[key] = value # Write to enhanced main dict
            else:
                if not subdict_name in enhanced: enhanced[subdict_name] = {} 
                enhanced[subdict_name].update(ext_dict) # Write to the the subdict in enhanced

        def add_txt_enh(key, rawstr,_pv = False):
            wstr = rawstr.format(**enhanced)
            enhstr = cbsv.conv_numstr(wstr)
            return add_enh(key,enhstr,rep_ext,"rep_ext",pv = _pv)
        
        def add_calc_enh(key, rawstr, _pv = False):
            flt = round(float(rawstr),2)
            return add_enh(key,flt,l_calc_ext,"calc_ext", pv = _pv, overwrite = True)

        def needs_txt_enh(tmp,csk):
            states = tmp["states"]
            return csk in states

        def needs_calc(state):
            return "calcs" in state

        def add_formula_conditional_vars(f,vd):
            ret = {}
            # This assumes all conditions are joined by AND
            conds = f["conditions"]
            for cond in conds:
                k, v, setval = cond
                if not k in vd:
                    print("ERROR {} not in info".format(k))
                    return False
                
                met = (vd[k] == v) # Simple match
                vkey, tval, fval = setval
                ret[vkey] = tval if met else fval

            vd.update(ret)
            return

        # Big method.
        # Takes in a formula (dict)
        # Returns a value of the result
        def resolve_formula(f):
            reqvar_key = "req_vars"
            opvar_key = "optional_vars"
            def op_on_all(vnames, op, vdic):
                def operate(a,b,op):
                    a = float(a) # Force everything here to float
                    b = float(b)
                    if 0: print("a,b", a, b) # DEBUG statement
                    return op(a,b)
                out = None
                for vname in vnames:
                    isnumbr = cbsv.is_number(vname)
                    rel_val = vname if isnumbr else vdic[vname]
                    if out == None:
                        out = rel_val
                    else:
                        out = operate(out,rel_val,op)
                return out
                
            instr = f["steps"]
            steps = list(instr.keys())
            steps = list(map(lambda x: (x.split(","), instr[x]),steps))
            steps.sort(key=lambda t: float(t[0][0])) # If no conversion it sorts as string
            if DEBUG: print("<RESOLVE FORMULA> aft sort",steps)
            req_vars = f[reqvar_key]
            op_vars = f.get(opvar_key, [])
            vd = dive_for_values(req_vars,enhanced)
            op_vars_d = dive_for_values(op_vars, enhanced,failzero=True)
            vd.update(op_vars_d)

            # Conditional values
            add_formula_conditional_vars(f,vd)
            if DEBUG: print("<RESOLVE FORMULA> vd",vd)

            #CALCULATIONS 
            vd["OUTCOME"] = 0
            for stp in steps:
                (NA, opname),(valnames,tkey)  = stp
                opname.replace(" ","")
                if not tkey in vd:
                    vd[tkey] = 0

                if opname == "add":
                    opr = lambda a,b: a+b
                elif opname == "multi":
                    opr = lambda a,b: a*b
                elif opname == "sub":
                    opr = lambda a,b: a-b
                elif opname == "div":
                    opr = lambda a,b: a/b
                elif opname == "equals":
                    opr = lambda a,b: (1 if a == b else 0)
                elif opname == "isgreater":
                    opr = lambda a,b: (1 if a > b else 0)
                else:
                    opr = lambda a,b: a
                vd[tkey] = op_on_all(valnames,opr,vd)
            return vd["OUTCOME"]

        ### MAIN METHOD LOGIC ###
        # Calculations
        if needs_calc(curr_state):
            state_calcs = curr_state["calcs"]
            for fname in state_calcs:
                print("performing",fname)
                if not fname in calcDB:
                    print("<RESOLVE FORMULA> ERROR! No such formula:{}".format(fname))
                else:
                    formula = calcDB[fname]
                    pv_flag = formula.get("persist_value",False)
                    target_key = formula["writeto"]
                    result = resolve_formula(formula)
                    add_calc_enh(target_key,result,pv_flag)
                if 1: print("<Intermediate> enh",enhanced)

        else:
            if DEBUG: print("No calculation performed")

        if DEBUG: print("postcalc enh",enhanced)

        # Message extensions and formatting
        # Template in format database
        for tmp in formatDB:
            if needs_txt_enh(tmp,cskey):
                target_key = tmp["writeto"]
                lookout = tmp["lookfor"].copy()
                vd = dive_for_values(lookout, enhanced, failzero=True) # Failzero true for rep ext
                
                if DEBUG: print("TMP",tmp)

                if "if_present" in tmp:
                    ifpr = tmp["if_present"]
                    for deet in list(ifpr.keys()):
                        enstr = ifpr[deet]
                        add_txt_enh(target_key,enstr)
                
                if "if_value" in tmp:
                    ifvl = tmp["if_value"]
                    for deet in list(ifvl.keys()):
                        if not deet in vd:
                            continue
                        formatmap = ifvl[deet]
                        if isinstance(vd[deet],list):
                            # E.g. reqinfo is a list
                            contents = vd[deet]
                        else:
                            contents = [vd[deet]]

                        for deetval in contents:
                            dstr = str(cbsv.conv_numstr(deetval,wantint=1)) # Because json keys can only be str
                            if dstr in formatmap:
                                enstr = formatmap[dstr]
                            else:
                                enstr = formatmap.get("DEFAULT",False)
                                if not enstr:
                                    raise Exception("<ENHANCE IF VAL> Error {} not in {}".format(dstr,formatmap))
                                    
                            add_txt_enh(target_key,enstr)
        
        # info.update(enhanced) # Write to info
        return (enhanced, topup)

    # Returns the a reply database either from intent or from state
    def getreplydb(self, intent, curr_state, issamestate):
        def get_hflag(obj):
            # Default is true
            hflag = True

            if "humanify" in obj:
                hflag = obj["humanify"]

            return hflag

        def get_replylist(obj):
            if DEBUG: print("<replydb> Pulling reply from:", obj["key"])
            return obj["replies"]
    
        LOCALDEBUG = 0 or DEBUG
        
        if LOCALDEBUG: print("csk", curr_state["key"],curr_state["thread"])

        # Decides priority of lookup. 
        # If same state flagged, look at intents first
        # Else look at state based replies
        lookups = [intent, curr_state] if issamestate else [curr_state, intent]

        rdb = []
        for obj in lookups:
            if obj == cbsv.NO_INTENT():
                # This is for when no intent
                continue

            if rdb == []:
                rdb = get_replylist(obj)
                self.hflag = get_hflag(obj)
            else:
                break
        
        if LOCALDEBUG: print("rdb:",rdb)

        if rdb == []:
            rdb = self.default_confused # OP

        return rdb

    # Generates a pure reply
    def generate_reply_message(self, rdb, info):
        def rand_response(response_list):
            return random.choice(response_list)
        def _humanify(msg, i):
            return self.humanizer.humanify(msg,i)

        reply_template = rand_response(rdb)
        if DEBUG: print("template",reply_template)
        final_msg = reply_template
        if isinstance(info, dict):
            if DEBUG: print("Enhanced info:",info)
            
            # Uses kwargs to fill this space
            final_msg = reply_template.format(**info)

        if self.hflag: final_msg = _humanify(final_msg, info)
        return final_msg

# Deals only with text
# Does not deal with state or information
class Chat:
    def __init__(self,chatID, convo_history = {}):
        self.chatID = chatID
        self.blank_chatlot = []
        self.curr_chatlog = self.blank_chatlot.copy()
        self.convo_history = convo_history
        self.convo_index = 0
        self.save_chat_logs = True
        # self.info = {}

    def getID(self):
        return self.chatID

    # Records conversation
    def record_messages(self, recieved, sent):
        dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        username = self.chatID + "(客户)"
        humanify = lambda user, m: dt+ " > " + user + ": " + m
        robotify = lambda x: dt + " > " + "机器人: " + x
        self.curr_chatlog.append(humanify(username, recieved))
        self.curr_chatlog.append(robotify(sent))
        self.convo_index = self.convo_index + 2

    def pop_prev_msg(self):
        # TODO failsafe when empty?
        # Need to get the previous previous message
        if self.convo_index < 2:
            return
        return self.curr_chatlog[self.convo_index - 2]
    

    ## TODO Database interaction?
    def get_previous_issues(self):
        pass
        # return self.user.get_issues()

    # Writes to a file eventually
    def record_to_database(self):
        if self.save_chat_logs:
            log = self.get_chatlog()
            chatid = self.chatID
            chatbot_be.record_chatlog_to_json(chatid, log)
            self.clear_chatlot()
        return

    def get_chatlog(self):
        return self.curr_chatlog

    def clear_chatlot(self):
        self.curr_chatlog = self.blank_chatlot.copy()
        return