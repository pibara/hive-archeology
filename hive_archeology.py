#!/usr/bin/python3
"""Hive Archaeology tool for voting on timeless content"""
import time
import json
import os
import argparse
import operator
from datetime import datetime
import dateutil
from lighthive.client import Client
from lighthive.datastructures import Operation
from lighthive.exceptions import RPCNodeException

VERSION = "0.1.4"
AUTHORS = {}
AUTHORS["hive-archology"] = ["pibara", "croupierbot"]
AUTHORS["lighthive"] = ["emrebeyler", "emrebeyler"]

def make_body(author, benef, curation_rewards):
    ben2prod = {}
    for key, val in AUTHORS.items():
        ben2prod[val[1]] = key
    rval = """This is a [hive-archeology](https://github.com/pibara/hive-archeology) proxy comment meant as a proxy for upvoting good content that is past it's initial pay-out window.

![image.png](https://files.peakd.com/file/peakd-hive/pibara/EppQ5vutzcx8r5YZ2LiXjW7EnMtgkcam6KpByUfiojAYYXLBmKFTC1jom5Kig1H9Z1w.png)

<sub><sup>Pay-out for this comment is configured as followed:</sup></sub>

| <sub><sup>role</sup></sub> | <sub><sup>account</sup></sub> | <sub><sup>percentage</sup></sub> | <sub><sup>note</sup></sub>|
| --- | --- | --- | --- |
"""
    if curation_rewards:
        divider = 200
        rval += "| <sub><sup>curator</sup></sub> | <sub><sup>-</sup></sub> | <sub><sup>50.0%</sup></sub> | <sub><sup>curation rewards enabled</sup></sub> |"
    else:
        divider = 100
        rval += "| <sub><sup>curator</sup></sub> | <sub><sup>-</sup></sub> | <sub><sup>0.0%</sup></sub> | <sub><sup>curation rewards disabled</sup></sub> |\n"
    for beneficiary in benef:
        share = beneficiary.get("weight",0) / divider
        if beneficiary.get("account","") == author:
            rval += "| <sub><sup>author</sup></sub> | <sub><sup>@"
            rval += author
            rval += "</sup></sub> | <sub><sup>"
            rval += str(share)
            rval += "%</sup></sub> | <sub><sup></sup></sub> |\n"
        elif beneficiary.get("account","") in ben2prod:
            prod = ben2prod[beneficiary["account"]]
            rval += "| <sub><sup>dev</sup></sub> | <sub><sup>@"
            rval += beneficiary["account"]
            rval += "</sup></sub> | <sub><sup>"
            rval += str(share)
            rval += "%</sup></sub> | <sub><sup>author of "
            rval += prod
            rval += "</sup></sub> |\n"
    return rval

class Voter:
    """The voter votes at most once every two minutes on posts marked for vote not shorter than two minutes ago"""
    def __init__(self, account, wif, printer):
        self.account = account
        self.wif = wif
        self.current = []
        self.last_vote = time.time()
        self.printer = printer

    def vote(self, account, permlink, weight):
        """Add a vote to the queue"""
        self.printer.notice("Adding voting action to queue")
        self.current.append([account, permlink, weight, time.time()])

    def tick(self):
        """Tick gets called once in a while, never more often than once every 10 seconds,
           here is where the actual voting happens."""
        # Check if the start of the queu contains a candidate that we can now upvote,
        # This means the candidate was queued at least two minutes ago, and the last upvote
        # action was also at least two minutes ago.
        if (time.time() - self.last_vote > 120 and
                self.current and
                time.time() - self.current[0][3] > 120):
            self.printer.notice("Casting vote")
            # Create the upvote operation
            operation = Operation(
                    'vote', {
                        "voter": self.account,
                         "author": self.current[0][0],
                         "permlink": self.current[0][1],
                        "weight": self.current[0][2],
                    })
            # Pop the candidate from the queue
            remember = self.current[0]
            self.current = self.current[1:]
            # Do the upvote
            try:
                Client(keys=[self.wif]).broadcast(operation)
                self.printer.notice("Vote casted")
            except RPCNodeException as exp:
                if "identical" in str(exp):
                    self.printer.warning("IDENTICAL")
                else:
                    self.printer.error("VOTE ERROR:", exp)
                    # add failed fote to end of the queue, maybe it will work if we try again later.
                    self.current.append(remember)

        if self.current:
            self.printer.notice("Votes left in vote-queue:", len(self.current))

class Commenter: # pylint: disable=too-few-public-methods
    """Class that makes upvote-proxy comments, if needed, and marks them for upvote"""

    def __init__(self, voter, account, wif, tool_creator_share, curation_rewards, printer): # pylint: disable=too-many-arguments
        self.voter = voter
        self.account = account
        self.wif = wif
        self.tool_creator_share = tool_creator_share
        self.curation_rewards = curation_rewards
        self.printer = printer

    def comment(self, author, permlink, weight): # pylint: disable=too-many-locals, too-many-branches, too-many-statements
        """Check is an active proxy comment exists, and if not, create one. Either way, mark for upvote by voter"""
        candidate = None
        self.printer.notice("Looking for candidate reward comment in post comments")
        # Find out if someone else also upvoted this very historic post recently enough to use the proxy comment that user made
        try:
            comments = Client().get_content_replies(author, permlink)
        except RPCNodeException as exp:
            self.printer.error(exp)
            comments = []
        for comment in comments: # pylint: disable = too-many-nested-blocks
            # One candidate is enough
            if candidate is None: # pylint: disable=too-many-statements
                # Fetch the last timeout time to check if a payout already occured
                last_payout = 0
                try:
                    last_payout =  dateutil.parser.parse(comment.get("last_payout", "2020-12-31T23:59:59")).timestamp()
                except RPCNodeException as exp:
                    self.printer.error(exp)
                    last_payout = time.time()
                if last_payout < 24 * 3600: # no payout yet, this might be a candidate
                    self.printer.info("Candidate comment hasn't been paid out yet")
                    beneficiaries = comment.get("beneficiaries", [])
                    allow_curation_rewards = comment.get("allow_curation_rewards", False)
                    total_ben_cnt = 0
                    total_ben_val = 0
                    # Check if the comment has the post author set as (>=50%) beneficiary)
                    for beneficiary in beneficiaries:
                        if beneficiary.get("account", "") == author:
                            self.printer.info("- candidate comment has post author as beneficiary")
                            if (beneficiary.get("weight", 0) > 7999 or
                                    (allow_curation_rewards and beneficiary.get("weight", 0) > 5999)):
                                self.printer.notice("- candidate has a sufficient reward share going to the post author")
                            else:
                                self.printer.notice("- candidate has insufficient share going to post author, no match")
                    # check if all beneficiaries match either the post author or one of the devs
                    valid_beneficiaries = {author}
                    total_ben_cnt = 0
                    total_ben_val = 0
                    for _, value in AUTHORS.items():
                        valid_beneficiaries.add(value[1])
                    all_ok = True
                    for beneficiary in beneficiaries:
                        if beneficiary.get("account", "") not in valid_beneficiaries:
                            all_ok = False
                        total_ben_val += beneficiary.get("weight", 0)
                        total_ben_cnt += 1
                    if all_ok:
                        self.printer.info("- all beneficiaries are expected beneficiaries")
                        if total_ben_cnt == 1 or total_ben_cnt == len(valid_beneficiaries):
                            self.printer.info("- valid amount of beneficiaries for comment")
                            if total_ben_val == 10000:
                                self.printer.notice("Benneficiary shares add up to 100%, MATCH")
                                candidate = [comment.get("author", None), comment.get("permlink", None)]
                        else:
                            self.printer.info("- invalid amount of beneficiaries for comment, no match")
                    else:
                        self.printer.notice("- at least one of the beneficiaries listed is unknown and unexpected, no match")
                else:
                    self.printer.info("Paid out already, no match")
        if candidate is None or candidate[0] is None or candidate[1] is None:
            # If no candidate was found, we create our own comment.
            self.printer.notice("No candidate comments found, creating a new comment")
            # Calculate the per-tool-author share.
            code_author_share = int(self.tool_creator_share * 100 / len(AUTHORS))
            # Calculate the share for the blog author
            post_author_share = 10000 - len(AUTHORS) * code_author_share
            # Create the beneficiaries list
            benef = [{"account": author, "weight": post_author_share }]
            if code_author_share:
                for _, val in AUTHORS.items():
                    if val[1] != author:
                        benef.append({"account": val[1], "weight": code_author_share})
                    else:
                        benef[0]["weight"] += code_author_share
            benef = sorted(benef, key=operator.itemgetter('account'))
            # Compose the comment body
            body = make_body(author, benef, self.curation_rewards)
            # Create a new comment permlink, and set it as our matching upvote candidate
            com_permlink = author.replace(".","-") + "-" + permlink
            self.printer.notice(com_permlink)
            candidate = [self.account, com_permlink]
            # Compose the two operations needed to make the comment and set the beneficiaries.
            my_post = Operation('comment', {
                    "parent_author": author,
                    "parent_permlink": permlink,
                    "author": self.account,
                    "permlink": com_permlink,
                    "title": "Hive Archeology comment",
                    "body": body,
                    "json_metadata": json.dumps({
                        "tags": ["hivearcheology"],
                        "app": "HiveArcheology " + VERSION
                        })
            })
            my_options = Operation('comment_options', {
                    "author": self.account,
                    "permlink": com_permlink,
                    "max_accepted_payout": "1000.000 HBD",
                    "percent_hbd": 0,
                    "allow_votes": True,
                    "allow_curation_rewards": self.curation_rewards,
                    "extensions": [
                    [ 0, { "beneficiaries": benef }] ]
            })
            # Post the comment with proper options.
            full_failure = False
            try:
                Client(keys=[self.wif]).broadcast([my_post, my_options])
            except RPCNodeException as exp:
                self.printer.error("Post failed, trying again in two minutes", exp)
                time.sleep(120)
                try:
                    Client(keys=[self.wif]).broadcast([my_post, my_options])
                except RPCNodeException as exp2:
                    self.printer.error(exp2)
                    full_failure = True
            if full_failure:
                self.printer.error("Post failed a second time, giving up")
            else:
                self.printer.notice("New archeology comment created")
                time.sleep(4)
                # Queue the candidate for upvoting in a few minutes
                self.voter.vote(candidate[0], candidate[1],weight)

class Archology:
    """The core personal HIVE-Archeology bot"""
    def __init__(self, account, wif, tool_creator_share, curation_rewards, printer, slow): # pylint: disable=too-many-arguments
        self.account = account
        headno = None
        while headno is None:
            try:
                headno = Client().get_dynamic_global_properties()["head_block_number"]
            except RPCNodeException as exp:
                printer.error(exp)
                time.sleep(5)
        self.next = headno - 100
        self.prnt = printer
        self.slow = slow
        self.voter = Voter(account, wif, printer)
        self.commenter = Commenter(self.voter, account, wif, tool_creator_share, curation_rewards, printer)

    def upto_head(self): # pylint: disable=too-many-branches
        """Process new blocks upto head"""
        # Keep track of time spent in this method call
        start_time = time.time()
        # Get the current head block number for the HIVE chain
        headno = None
        while headno is None:
            try:
                headno = Client().get_dynamic_global_properties()["head_block_number"]
            except RPCNodeException as exp:
                self.prnt.error(exp)
                time.sleep(5)
        # Figure out how many blocks we need to process
        blocks_left = headno + 1 - self.next
        # Process blocks in groups of at most 100
        while blocks_left !=0: # pylint: disable=too-many-nested-blocks
            # Figure out if we need to process 100 blocks or less
            if blocks_left > 100:
                count = 100
                blocks_left -= 100
            else:
                count = blocks_left
                blocks_left = 0
            # Fetch the number of blocks that we need to process this time around
            blocks = None
            self.prnt.info("fetching blocks, count =", count)
            while blocks is None:
                try:
                    blocks = Client()('block_api').get_block_range({"starting_block_num": self.next, "count":count})["blocks"]
                except RPCNodeException as exp:
                    self.prnt.error(exp)
                    time.sleep(5)
            # Process the blocks one by one
            for block in blocks:
                if "transactions" in block:
                    for trans in block.get("transactions", []):
                        if "operations" in  trans:
                            # Process all the operations
                            for operation in  trans.get("operations", []):
                                op_type = operation.get("type", "none")
                                vals = operation.get("value", {})
                                # Process ony vote operations made by our owner.
                                if op_type == "vote_operation" and vals.get("voter", "") == self.account:
                                    self.prnt.info("Vote by owner detected:",
                                                   vals.get("author", ""),
                                                   vals.get("permlink",""))
                                    # Fetch the post that was voted on.
                                    try:
                                        content = Client()('bridge').get_post(
                                                {
                                                    "author": vals["author"],
                                                    "permlink": vals["permlink"]
                                                })
                                    except RPCNodeException as exp:
                                        self.prnt.error(exp)
                                        content = {}
                                    # We only need to process the upvote if the post has already had a pay-out
                                    if content.get("is_paidout", True):
                                        self.prnt.info("post reward has been paid out already, taking action")
                                        # Find a way to make the stale upvote actually count.
                                        self.commenter.comment(vals["author"], vals["permlink"], vals["weight"])
                    self.next += 1
            # Do a tiny one second sleep to avoid API overload.
            if blocks_left:
                time.sleep(1)
        # Return the time it took to process up to head.
        return time.time() - start_time

    def run(self):
        """Main run function for the bot"""
        while True:
            # Process all blocks upto head
            duration = self.upto_head()
            # If processing took less than 10 seconds, sleep for a bit
            if self.slow:
                sleeptime = 100 - duration
            else:
                sleeptime = 10 - duration
            if sleeptime > 0:
                self.prnt.info("waiting for :", sleeptime)
                time.sleep(sleeptime)
            # Do at most one pending vote that is waiting long enough
            self.voter.tick()

class Print:
    """Utility class for simple logging"""
    def __init__(self, printlevel):
        self.printlevel = printlevel

    def debug(self,*args,**kwargs):
        """Debug level print"""
        if not self.printlevel:
            print(datetime.now().isoformat().split(".")[0],"DEBUG:", *args, **kwargs)

    def info(self,*args,**kwargs):
        """Info level print"""
        if self.printlevel < 2:
            print(datetime.now().isoformat().split(".")[0],"INFO:",*args, **kwargs)

    def notice(self, *args,**kwargs):
        """Notice level print"""
        if self.printlevel  < 3:
            print(datetime.now().isoformat().split(".")[0],"NOTICE:", *args, **kwargs)

    def warning(self, *args,**kwargs):
        """Warning level print"""
        if self.printlevel < 4:
            print(datetime.now().isoformat().split(".")[0],"WARNING:", *args, **kwargs)

    def error(self, *args,**kwargs):
        """Error level print"""
        if self.printlevel < 5:
            print(datetime.now().isoformat().split(".")[0],"ERROR:", *args, **kwargs)

def _main():
    """Parse commandline and run the actual bot"""
    parser = argparse.ArgumentParser()
    parser.add_argument("account", help="HIVE account to run under")
    parser.add_argument("--curation-reward", help="Enable curation rewards (default false)", action="store_true")
    parser.add_argument("--tool-creator-share",
                        help="Percentage of creator share to go to tool/lib creator (default 5)",
                        type=int,
                        default=5)
    parser.add_argument("--printlevel",
                        help="Minimum level of severity for output to be printed (default 1)",
                        type=int,
                        default=1)
    parser.add_argument("--wif",
                        help="WIF of the posting key for the user the tool runs under (default to env usage)")
    parser.add_argument("--slow",
                        help="Poll new blocks every 100 seconds instead of every 10 seconds",
                        action="store_true")
    args = parser.parse_args()
    account = args.account
    wif = args.wif
    if wif is None:
        wif = os.environ.get(account.upper() + "_WIF",os.environ.get("HIVE_ARCHEOLOGY_WIF",None))
    if wif is None:
        wif = input("Posting key WIF for "+ account + ":").rstrip('\r\n')
    tool_creator_share = args.tool_creator_share
    # Creator share can not be set lower than 0% and not higher than 20% .
    tool_creator_share = min(tool_creator_share, 20)
    tool_creator_share = max(tool_creator_share, 0)
    # Tool creator share is of total, so double it (as share of creator reward) if curation rewards are enabled.
    if args.curation_reward:
        tool_creator_share *= 2
    prnt = Print(args.printlevel)
    bot = Archology(account, wif, tool_creator_share, args.curation_reward, prnt, args.slow)
    bot.run()

if __name__ == "__main__":
    _main()
