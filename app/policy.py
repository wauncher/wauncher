"""The Info page: what wauncher does with your accounts, and where third-party launchers stand with CCP.

Kept as data so README.md and the in-app Info page say the same thing.
"""

SUMMARY = (
    "wauncher is a third-party launcher. It does not touch the game client, its files, its memory or its "
    "traffic, and it never sends input to a client. It only does what the official launcher does before a "
    "client starts: exchange the account's refresh token for a short-lived access token at CCP's SSO, "
    "then start exefile.exe with the same arguments the official launcher uses. Everything after that is "
    "the unmodified EVE client talking to CCP."
)

# (heading, paragraphs)
SECTIONS = [
    ("What CCP allows and forbids", [
        "CCP does not approve or certify any third-party software; every tool is used at your own risk. Its "
        "published policy draws the line at software that modifies the client, automates play, or confers an "
        "unfair advantage. Convenience tooling around the client is a different category, and CCP has said so "
        "in as many words.",
        "In the 25 November 2014 statement that made input broadcasting and input multiplexing bannable "
        "(CCP Falcon, EVE Online forums), CCP listed the things that stay allowed because they have no impact on "
        "the EVE universe and are done for convenience: EVE Online client settings, window positions and "
        "arrangements, and the login process. That list is CCP's own carve-out from its strictest rule. Starting "
        "clients and logging accounts in is exactly the \"login process\", and wauncher does not even broadcast "
        "input to do it.",
        "The same statement, and CCP's Third Party Policies page, keep multiboxing itself legal: running many "
        "clients at the same time is fine. What is banned is one keypress or click being sent to more than one "
        "client (input broadcasting / multiplexing), and any automation of play. wauncher does neither. It starts "
        "processes and then has nothing further to do with them.",
    ]),
    ("Precedent", [
        "Third-party launchers have existed openly for close to a decade. CCP's own launcher introduced the SSO "
        "token login in 2016, and Lavish Software's open-source ISBoxer EVE Launcher (ISBEL) followed that same "
        "year, built on CCP's flow; it is still maintained and is discussed on the official EVE forums without "
        "sanction. IsBridgeUp on GitHub is another open-source launcher using the same token flow. wauncher does "
        "exactly what those tools do.",
    ]),
    ("What wauncher never does", [
        "No reading or writing of client memory, no modified client files, no packet inspection, no cache "
        "scraping, no input sent to clients, no automation of anything inside the game. The one CCP endpoint "
        "used is the public SSO token endpoint, with the official launcher's own client id and refresh token.",
    ]),
    ("Your tokens", [
        "Refresh tokens are imported from the official launcher's state (which you already hold on this "
        "machine) and stored in tokens.dat under %LOCALAPPDATA%\\eve-wauncher, protected with Windows DPAPI so "
        "only your Windows user can read them. Access tokens live 10 to 20 minutes and are stored the same way. "
        "Nothing is ever written back into the official launcher's files except by the Restore feature, which "
        "you trigger yourself.",
    ]),
    ("Sources", []),
]

SOURCES = [
    ("CCP - Third Party Policies (support article by Lead GM Carbon)",
     "https://support.eveonline.com/hc/en-us/articles/8564030965660-Third-Party-Policies"),
    ("CCP - Third party applications (support article)",
     "https://support.eveonline.com/hc/en-us/articles/5888034246428-Third-party-applications"),
    ("CCP Falcon, 25 Nov 2014 - update regarding multiboxing and input automation (forum post, mirrored)",
     "https://evenews24.com/2014/11/25/ccp-falcon-update-regarding-multiboxing-and-input-automation/"),
    ("PCGamesN coverage of the 2014 ruling",
     "https://www.pcgamesn.com/eve-online/eve-online-input-broadcasting-and-input-multiplexing-become-permaban-offences"),
    ("CCP Stillman, 18 Apr 2013 - Client modification, the EULA and you (dev blog)",
     "https://www.eveonline.com/news/view/client-modification-the-eula-and-you"),
    ("Lavish Software - ISBoxer EVE Launcher (open source, on GitHub)",
     "https://github.com/LavishSoftware/ISBoxerEVELauncher"),
    ("ISBoxer forums, Sep 2016 - ISBoxer EVE Launcher announced as an open-source EVE launcher",
     "https://isboxer.com/forum/viewtopic.php?f=8&t=8142"),
    ("EVE Online forums - ISBoxer EVE Launcher thread",
     "https://forums.eveonline.com/t/isboxer-eve-launcher/332101"),
    ("IsBridgeUp - open-source third-party EVE launcher with SSO token login",
     "https://github.com/Playos/IsBridgeUp"),
    ("EVE Online EULA",
     "https://support.eveonline.com/hc/en-us/articles/8413329735580-EVE-Online-End-User-License-Agreement"),
]

DISCLAIMER = (
    "This is a summary of public CCP statements, not legal advice, and CCP can change its policies at any "
    "time. Read the current EULA and Third Party Policies yourself. Use at your own risk."
)
