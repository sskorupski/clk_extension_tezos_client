# clk tezos-client 
While playing with the [tezos](https://tezos.com/) block chain, **clk tezos-client** aims to make it easier to use the [tezos-client](https://tezos.gitlab.io/shell/cli-commands.html) command. 

The goal is to offer:
* Use interactive commands with auto-completion.
* Allow both usage of address or alias.
* Make easier to share your keys (_ex: when working on testnet in a team_)
* Use JSON for token metadata-description

## Setup 
Either:

* install [clk-project](https://github.com/clk-project) and the extension with
```bash 
curl -sSL https://clk-project.org/install.sh | env CLK_EXTENSIONS=https://github.com/sskorupski/clk_extension_tezos_client bash
```
* if you already have [clk-project](https://github.com/clk-project), you can simply install this extension with
```bash
clk extension install https://github.com/sskorupski/clk_extension_tezos_client
```

## Nota bene
* This is an early experimental version. :scream:
* Feel free to kindly open issues. :kissing_heart:
* Improve the tool :sunglasses:

## TODO
* [ ] Remove the `exec_command` usages
* [ ] Clean logs and print usage
* [ ] Handle dry-run 
* [ ] Install without the `install-smartpy.sh` script
* [ ] Command for Smartpy-cli version
* [ ] Uninstall Smartpy-cli:
```bash
ifneq ($(shell test -s ~/smartpy-cli || echo false), false)
	rm -r ~/smartpy-cli
	echo "smartpy-cli successfully uninstalled!"
else
	echo "smartpy-cli is not installed"
endif 
```

* [ ] Command `update` = `uninstall` + `install`

* [ ] Uninstall tezos-client:
```bash
ifneq ($(shell test -s ~/.local/bin/tezos-client || echo false), false)
	rm ~/.local/bin/tezos-client
	echo "tezos-client successfully uninstalled!"
else
	echo "tezos-client is not installed"
endif
```

* [ ] Auto-completion for ZSH