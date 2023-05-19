#!/usr/bin/python3
import time
import json
import os
import argparse
import operator
import dateutil.parser
from lighthive.client import Client
from lighthive.datastructures import Operation
from lighthive.exceptions import RPCNodeException

AUTHORS = {}
AUTHORS["hive-archology"] = ["pibara", "croupierbot"]
AUTHORS["lighthive"] = ["emrebeyler", "emrebeyler"]

class Voter:
    """The voter votes at most once every two minutes on posts marked for vote not shorter than two minutes ago"""
    def __init__(self, account, wif):
        self.account = account
        self.wif = wif
        self.current = []
        self.last_vote = time.time()

    def vote(self, account, permlink, weight):
        """Add a vote to the queue"""
        print("NOTICE: Adding voting action to queue")
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
            print("NOTICE: Casting vote")
            # Create the upvote operation
            op = Operation('vote', {
                    "voter": self.account,
                    "author": self.current[0][0],
                    "permlink": self.current[0][1],
                    "weight": self.current[0][2],
                 })
            # Pop the candidate from the queue
            self.current = self.current[1:]
            # Do the upvote
            try:
                Client(keys=[self.wif]).broadcast(op)
                print("NOTICE: Vote casted")
            except RPCNodeException as exp:
                if "identical" in str(exp):
                    print("WARNING: IDENTICAL")
                else:
                    print("ERROR: VOTE ERROR:", exp)

class Commenter:
    """Class that makes upvote-proxy comments, if needed, and marks them for upvote"""

    def __init__(self, voter, account, wif, tool_creator_share, curation_rewards):
        self.voter = voter
        self.account = account
        self.wif = wif
        self.tool_creator_share = tool_creator_share
        self.curation_rewards = curation_rewards

    def comment(self, author, permlink, weight):
        """Check is an active proxy comment exists, and if not, create one. Either way, mark for upvote by voter"""
        candidate = None
        print("INFO: Looking for candidate reward comment in post comments")
        # Find out if someone else also upvoted this very historic post recently enough to use the proxy comment that user made
        for comment in Client().get_content_replies(author, permlink):
            # One candidate is enough
            if candidate is None:
                # Fetch the last timeout time to check if a payout already occured
                last_payout = 0
                try:
                    last_payout =  dateutil.parser.parse(comment.get("last_payout", "2020-12-31T23:59:59")).timestamp()
                except:
                    pass
                if last_payout < 24 * 3600: # no payout yet, this might be a candidate
                    print("INFO: Candidate comment hasn't been paid out yet")
                    beneficiaries = comment.get("beneficiaries", [])
                    has_author = False
                    total_ben_cnt = 0
                    total_ben_val = 0
                    # Check if the comment has the post author set as (>=50%) beneficiary)
                    for beneficiary in beneficiaries:
                        if beneficiary.get("account", "") == author and beneficiary.get("weight", 0) > 4999:
                            has_author = True
                            total_ben_val = beneficiary.get("weight", 0)
                    if has_author:
                        print("NOTICE: Possible candidate comment, author as beneficiary for 50% or more")
                    # Check if either all tool authors (this includes the author of the lighthive library)
                    #  or none of the authors (0% is a valid way to run the bot) are there as beneficiaries.
                    if len(beneficiaries) == len(AUTHORS) + 1 and has_author:
                        for _, value in AUTHORS.items():
                            for beneficiary in beneficiaries:
                                if beneficiary.get("account", "") == value[1]:
                                    total_ben_val += beneficiary.get("weight", 0)
                                    total_ben_cnt += 1
                    # check if next to the above, 100% of creator share is defined as beneficiaries.
                    if ((len(beneficiaries) == len(AUTHORS) + 1 and len(AUTHORS) == total_ben_cnt) or len(beneficiaries) == 1) and total_ben_val == 10000:
                        print("NOTICE: Definite candidate, no unexpected beneficiaries and total adds up to 100%")
                        # Set the found post as matching candidate
                        candidate = [comment["author"], comment["permlink"]]
                    else:
                        print("NOTICE: Candidate didn't add up.")
                else:
                    print("INFO: Not a viable candidate, paid out already")
        if candidate is None:
            # If no candidate was found, we create our own comment.
            print("INFO: No candidate comments found, creating a new comment")
            # Calculate the per-tool-author share.
            code_author_share = int(self.tool_creator_share * 100 / len(AUTHORS))
            # Calculate the share for the blog author
            post_author_share = 10000 - len(AUTHORS) * code_author_share
            # Create the beneficiaries list
            benef = [{"account": author, "weight": post_author_share }]
            for _, val in AUTHORS.items():
                if val[1] != author:
                    benef.append({"account": val[1], "weight": code_author_share})
                else:
                    benef[0]["weight"] += code_author_share
            benef = sorted(benef, key=operator.itemgetter('account'))
            # Compose the comment body
            body = "This comment was made by a [hive-archeology]("
            body += "https://github.com/pibara/hive-archeology"
            body += ") bot running under the control of @" + self.account + "\n"
            body += "![image.png](https://files.peakd.com/file/peakd-hive/pibara/EogNjuKR1hbkUH9Vxo4UdfD7er5u4MfSoDZJHyJGmwwvUmnASTNGukBzcAbMXnzGwQH.png)\n"
            body += " The goal of this comment is to act as reward proxy for up-voting valuable timeless content on HIVE"
            body += " for what the one-week upvote window has closed.\n"
            body += "The bot script is currently pre-beta.\n"
            # Create a new comment permlink, and set it as our matching upvote candidate
            com_permlink = author + "-" + permlink
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
                        "app": "HiveArcheology 0.0.3"
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
            # FIXME: error handling
            # Post the comment with proper options.
            Client(keys=[self.wif]).broadcast([my_post, my_options])
            print("NOTICE: new archeology comment created")
            print("NOTICE: new archeology comment_options set")
        # Queue the candidate for upvoting in a few minutes
        self.voter.vote(candidate[0], candidate[1],weight)

class Archology:
    """The core personal HIVE-Archeology bot"""
    def __init__(self, account, wif, tool_creator_share, curation_rewards):
        self.account = account
        headno = None
        while headno is None:
            try:
                headno = Client().get_dynamic_global_properties()["head_block_number"]
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        self.next = headno - 100
        self.voter = Voter(account, wif)
        self.commenter = Commenter(self.voter, account, wif, tool_creator_share, curation_rewards)

    def upto_head(self):
        """Process new blocks upto head"""
        # Keep track of time spent in this method call
        start_time = time.time()
        # Get the current head block number for the HIVE chain
        headno = None
        while headno is None:
            try:
                headno = Client().get_dynamic_global_properties()["head_block_number"]
            except RPCNodeException as exp:
                print(exp)
                time.sleep(5)
        # Figure out how many blocks we need to process
        blocks_left = headno + 1 - self.next
        # Process blocks in groups of at most 100
        while blocks_left !=0:
            # Figure out if we need to process 100 blocks or less
            if blocks_left > 100:
                count = 100
                blocks_left -= 100
            else:
                count = blocks_left
                blocks_left = 0
            # Fetch the number of blocks that we need to process this time around
            blocks = None
            print("INFO: fetching blocks, count =", count)
            while blocks is None:
                try:
                    blocks = Client()('block_api').get_block_range({"starting_block_num": self.next, "count":count})["blocks"]
                except RPCNodeException as exp:
                    print(exp)
                    time.sleep(5)
            # Process the blocks one by one
            for block in blocks:
                if "transactions" in block:
                    for trans in block["transactions"]:
                        if "operations" in  trans:
                            # Process all the operations
                            for operation in  trans["operations"]:
                                op_type = operation["type"]
                                vals = operation["value"]
                                # Process ony vote operations made by our owner.
                                if op_type == "vote_operation" and vals["voter"] == self.account:
                                    print("INFO: Vote by owner detected:", vals["author"], vals["permlink"])
                                    # FIXME: Error handling
                                    # Fetch the post that was voted on.
                                    content = Client()('bridge').get_post({"author": vals["author"], "permlink": vals["permlink"]})
                                    # We only need to process the upvote if the post has already had a pay-out
                                    if content["is_paidout"]:
                                        print("NOTICE: post reward has been paid out already, taking action")
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
            sleeptime = 10 - duration
            if sleeptime > 0:
                print("INFO: waiting for :", sleeptime)
                time.sleep(sleeptime)
            # Do at most one pending vote that is waiting long enough
            self.voter.tick()

def _main():
    """Parse commandline and run the actual bot"""
    parser = argparse.ArgumentParser()
    parser.add_argument("account", help="HIVE account to run under")
    parser.add_argument("--curation-reward", help="Enable curation rewards (default false)", action="store_true")
    parser.add_argument("--tool-creator-share", help="Percentage of creator share to go to tool/lib creator (default 5)", type=int, default=5)
    parser.add_argument("--wif", help="WIF of the posting key for the user the tool runs under (default to env usage)")
    args = parser.parse_args()
    account = args.account
    wif = args.wif
    if wif is None:
        wif = os.environ.get(account.upper() + "_WIF",os.environ.get("HIVE_ARCHEOLOGY_WIF",None))
    if wif is None:
        wif = input("Posting key WIF for "+ account + ":").rstrip('\r\n')
    tool_creator_share = args.tool_creator_share
    # Creator share can not be set lower than 0% and depending on the curation_reward setting, not higher than 25% or 50%.
    if args.curation_reward:
        tool_creator_share = min(tool_creator_share, 50)
    else:
        tool_creator_share = min(tool_creator_share, 25)
    tool_creator_share = max(tool_creator_share, 0)
    bot = Archology(account, wif, tool_creator_share, args.curation_reward)
    bot.run()

if __name__ == "__main__":
    _main()
