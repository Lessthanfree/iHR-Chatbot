import json
import os
from chatbot_supp import SIP, Policy, InfoVault, InfoParser
from chatclass import DetailManager, ReplyGenerator, PolicyKeeper

def read_json(json_filename):
    with open(json_filename, 'r') as f:
        data = json.loads(f.read())
    return data

# Converts a dict of states to a dict of state keys
def state_key_dict(states):
    ks = states.keys() # These are strings
    out = {}
    for k in ks:
        out[k] = states[k]["key"]
    return out

def init_replygen(jdata):
    INTENTS = jdata["intents"]
    STATE_KEYS = state_key_dict(jdata["states"])
    REPLY_DB = jdata["reply_db"]

    # Actually empty but I'm leaving a template here
    STS_REPLY_KEY_LOOKUP = {
        (STATE_KEYS['payment'], STATE_KEYS['finish_sale']): "r_sale_done"
    }

    SS_REPLY_KEY_LOOKUP = {
        STATE_KEYS["propose_plan"]: "r_state_details",
        STATE_KEYS['confirm_plan']: "r_confirm_plan",
        STATE_KEYS['payment']: "r_confirm_price",
        STATE_KEYS['finish_sale']: "r_sale_done",
        STATE_KEYS['recv_info']: "r_req_info",
        STATE_KEYS['init_sale']: "r_sales_intro",
        STATE_KEYS['ask_if_issue']: "r_ask_if_issue"
    }

    INTENT_REPLY_KEY_LOOKUP = {}
    gen_reply_list = ["ask_name", "greet", "goodbye"]
    for i in gen_reply_list:
        intent = INTENTS[i]
        dbk = "r_"+str(i)
        INTENT_REPLY_KEY_LOOKUP[intent] = dbk
    rkey_dbs = {}
    rkey_dbs["s2s"] = STS_REPLY_KEY_LOOKUP
    rkey_dbs["ss"] = SS_REPLY_KEY_LOOKUP
    rkey_dbs["intent"] = INTENT_REPLY_KEY_LOOKUP
    
    return ReplyGenerator(REPLY_DB, rkey_dbs)

def init_policykeeper(jdata):
    INTENTS = jdata["intents"]
    STATES = jdata["states"]
    STATE_KEYS = state_key_dict(jdata["states"])
    MATCH_DB = jdata["match_db"]

    ### POLICIES ###

    default_policy_set = [
        (INTENTS['greet'], SIP.same_state()),
        (INTENTS['ask_name'],SIP.same_state()),
        (INTENTS['pay_query'],SIP.same_state()),
        (INTENTS['sales_query'],SIP.same_state()),
        (INTENTS['deny'], SIP.go_back_state()),
        (INTENTS['goodbye'], SIP(STATES["goodbye"])),
        (INTENTS['report_issue'], SIP(STATES['log_issue'], pocket_state = True)),
        (INTENTS['reset_chat'], SIP(STATES['init']))
    ]
    make_policy = lambda s_ints: Policy(default_policy_set,s_ints)

    POLICY_RULES = {
        STATE_KEYS['init']: make_policy([
            (INTENTS['deny'],SIP(STATES['init'])),
            (INTENTS['greet'],SIP(STATES['init'])),
            (INTENTS['gen_query'],SIP(STATES['confirm_query'])),
            (INTENTS['purchase'], SIP(STATES['init_sale'])),
            (INTENTS['pay_query'], SIP(STATES['pay_query'])),
            (INTENTS['sales_query'], SIP(STATES['sales_query']))
            ]
        ),
        STATE_KEYS['init_sale']: make_policy([
            (INTENTS['affirm'], SIP(STATES['propose_plan'])),
            (INTENTS['deny'], SIP(STATES['ask_if_issue']))
            ]
        ),
        STATE_KEYS['propose_plan']: make_policy([
            (INTENTS['affirm'], SIP(STATES['confirm_plan'])),
            (INTENTS['deny'], SIP(STATES['ask_if_issue']))
            ]
        ),
        STATE_KEYS['confirm_plan']: make_policy([
            (INTENTS['affirm'], SIP(STATES['payment'])),
            (INTENTS['deny'], SIP(STATES['ask_if_issue']))
            ]
        ),
        STATE_KEYS['ask_if_issue']: make_policy([
            (INTENTS['affirm'], SIP(STATES['log_issue'])),
            (INTENTS['deny'], SIP.goto_pending_state())
            ]
        ),
        STATE_KEYS['payment']: make_policy([
            (INTENTS['affirm'], SIP(STATES['finish_sale'])),
            (INTENTS['deny'], SIP(STATES['ask_if_issue']))
            ]
        )
    }

    # Loop to make all policies
    existing = list(POLICY_RULES.keys())
    for k in list(STATES.keys()):
        state_value = STATES[k]["key"]
        if state_value in existing:
            continue # Don't overwrite existing policy lookup values
        POLICY_RULES[state_value] = make_policy([])


    INTENT_LOOKUP_TABLE = {}
    for k in list(MATCH_DB.keys()):
        look_key = k[3:]
        kv = INTENTS[look_key]
        INTENT_LOOKUP_TABLE[kv] = MATCH_DB[k]

    return PolicyKeeper(POLICY_RULES, INTENT_LOOKUP_TABLE)

def init_infoparser(jdata):
    relevant = jdata["info_parser"]
    return InfoParser(relevant)

def init_detailmanager(jdata):
    vault = InfoVault(jdata)
    return DetailManager(vault)

def master_initalize(filename = ""):
    # INTENTS = jdata["intents"]
    # STATE_KEYS = jdata["state_keys"]
    # MATCH_DB = jdata["match_db"]
    direct = os.getcwd()
    absdirect = "/Users/davidgoh/Desktop/chatbot"
    if filename == "":
        filename = absdirect + "/"+ "chatbot_resource.json"

    print("reading from ",filename)
    jdata = read_json(filename)

    components = {}
    components["replygen"] = init_replygen(jdata)
    components["pkeeper"] = init_policykeeper(jdata)
    components["dmanager"] = init_detailmanager(jdata)
    components["iparser"] = init_infoparser(jdata)
    return components