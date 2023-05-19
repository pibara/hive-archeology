# hive-archeology
Simple HIVE bot that allows its owner to up-vote valuable timeless HIVE posts. 

To install the bot, run:

```
pip3 install hive-archeology-bot
```

To run the bot you will need the WIF of your HIVE posting key and your HIVE account name.

For info on basic usage, type:

```
hive-archeology-bot --help
```

You can supply the WIF on the command line, although this isn't recomended. A better way is to set the environment variable **HIVE_ARCHEOLOGY_WIF**.

If you plan to use multiple instances of the bot, each with its own HIVE account, then postfix an uppercase verson of your account name with an underscore and **WIF** and use that as envinronment variable name for your WIF. So if your account name is *hiveuser*, your environment variable should be named **HIVEUSER_WIF**.

After setting up your environment vars, the most basic use of the script is starting it with just your HIVE account name

```
hive-archeology-bot hiveuser
```

This will run the bot on your account with standard setting:

* No curation rewards enabled
* A combined share of the beneciciaries setting of 5% for the author of this private bot and the author of the lighthive library.

Let's ssay you want to get curation rewards from your upvotes, and you want to increase the share of the creator rewards for the developers to 10%, you can start the bot like this:

```
hive-archeology-bot hiveuser --curation-reward --tool-creator-share 10
```
