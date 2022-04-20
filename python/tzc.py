import glob
import json
import ntpath
import os
import readline
import shutil
import subprocess
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from shlex import split

import click
from clk.decorators import argument
from clk.decorators import group
from clk.decorators import option
from clk.lib import call, check_output, safe_check_output
from clk.log import get_logger
from distlib.compat import raw_input
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter

LOGGER = get_logger(__name__)


def exec_command(command, shell=False):
    LOGGER.info(command)
    args = command.split(' ')
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=shell)
    out, err = proc.communicate()
    return out, err, proc.returncode


@group()
def tzc():
    """Commands to play with tezos-client"""


class SmartPyCli:
    clk_install_script_path = str(Path.home()) + '/.config/clk/extensions/tezos_client/install-smartpy.sh'
    dir_path = str(Path.home()) + '/smartpy-cli/'
    script_path = dir_path + 'SmartPy.sh'


class TezosClient:
    clk_install_script_path = str(Path.home()) + '/.config/clk/extensions/tezos_client/install-tezos-client.sh'


def client_version():
    raw_version = safe_check_output([SmartPyCli.script_path, '--version'],
                                    stderr=subprocess.PIPE)
    return raw_version if 'SmartPy Version: ' not in raw_version else raw_version[len('SmartPy Version: '):].strip()


def install_smartpy_cli():
    call(['chmod', 'u+x', SmartPyCli.clk_install_script_path])
    click.echo(check_output([SmartPyCli.clk_install_script_path]))


def install_tezos_client():
    call(['chmod', 'u+x', TezosClient.clk_install_script_path])
    click.echo(check_output([TezosClient.clk_install_script_path]))


@tzc.command()
def install():
    """Install required dependencies such as tezos-client and smartpy-cli"""
    smpy_version = client_version()
    if smpy_version:
        LOGGER.info(f'smartpy-cli {smpy_version} detected: skip')
    else:
        install_smartpy_cli()

    tzc_version = safe_check_output(['tezos-client', '--version'])
    if tzc_version:
        LOGGER.info(f'tezos-clients {tzc_version} detected: skip')
    else:
        install_tezos_client()


@tzc.command()
def uninstall():
    """Remove required dependencies such as tezos-client and smartpy-cli"""
    smpy_version = client_version()
    if smpy_version:
        LOGGER.info("smartpy-cli detected: skip")
    install_smartpy_cli()


@tzc.group(name="network")
def tzc_network():
    """Configure tezos-client"""


@tzc_network.command(name="set")
@argument("rpc-link", envvar='RPC_LINK', help="RPC tezos node address")
def set_network(rpc_link):
    """Set the RPC tezos node address"""
    LOGGER.info(f'Configuring tezos-client network with {rpc_link}')
    call(["tezos-client", "--endpoint", rpc_link, "config", "update"])
    LOGGER.info(f'Result:')
    call(["tezos-client", "config", "show"], stderr=subprocess.DEVNULL)


def get_config():
    return json.loads(
        safe_check_output(split("tezos-client config show"))
    )


@tzc_network.command(name="show")
def show_config():
    """Show tezos-client configuration."""
    config = get_config()
    if "endpoint" in config:
        click.echo(config["endpoint"])


@tzc.group(name="account")
def tzc_account():
    """Play with accounts"""


@tzc_account.command(name="show")
@option("--no-contracts", default=False, is_flag=True, help="Do not show contracts accounts")
def show_accounts(no_contracts):
    """List configured accounts usable by the client."""
    kind = "addresses" if no_contracts else "contracts"
    click.echo(safe_check_output(split("tezos-client list known " + kind)))


@tzc.group()
def transfer():
    """Transfer coin or token"""


@transfer.command()
@argument("amount", help="amount taken from source to dest in ꜩ")
@argument("source", help="The account name to take the amount in ꜩ")
@argument("dest", help="The account name or literal address to send the amount in ꜩ")
def xtz(amount, source, dest):
    """Transfer coin or token"""
    call(["tezos-client", "transfer", amount, "from", source, "to", dest, "--burn-cap 0.5"])


@tzc.group()
def interactive():
    """Interactive commands"""


def get_accounts():
    cmd = subprocess.run(["tezos-client", "list", "known", "contracts"], capture_output=True)
    accounts = {}
    for line in cmd.stdout.split(b'\n'):
        account = line.split(b': ')
        if len(account) == 2:
            name = account[0].decode("utf-8")
            address = account[1].decode("utf-8")
            accounts[name] = address
    LOGGER.debug(accounts)
    return accounts


def get_account_names():
    names = []
    for name in get_accounts():
        names.append(name)
    return names


def get_address(name):
    accounts = get_accounts()
    if name in accounts.keys():
        return get_accounts()[name]
    raise Exception('No such account', name, 'do you mean one of:', accounts.keys())


@interactive.command(name="transfer-xtz")
def interactive_xtz_transfer():
    """Interactive XTZ transfer"""
    account_completer = WordCompleter(get_account_names())
    source = prompt('From account name: ', completer=account_completer)
    amount = prompt('XTZ Amount: ')
    dest = prompt('And transfer to (account name or address): ', completer=account_completer)
    subprocess.run(["tezos-client", "transfer", amount, "from", source, "to", dest, "--burn-cap", "0.5"])


def path_complete(text, state):
    return (glob.glob(text + '*') + [None])[state]


def hexencode(str):
    res = str.encode('utf-8').hex()
    return "0x" + res


def build_fa2_storage(adminAddress, metadata):
    res = '(Pair ' \
          '(Pair (Pair "' + adminAddress + '" 0) '  # admin
    res += '(Pair {} '  # ledger
    res += '(Pair {Elt "" ' + hexencode(metadata) + ' }'  # metadata
    res += '{}))) '  # operator
    res += '(Pair (Pair {} '  # (pair (big_map %owner_by_token_id nat address)
    res += '(Pair {} False))'  # (bool %paused)
    res += ' (Pair {} (Pair {} {}))))'  # %token_metadata %token_info %total_supply
    return res


@interactive.command(name="fa2-deploy")
def interactive_fa2_deploy():
    """Interactive FA2 contract deployment"""
    account_completer = WordCompleter(get_account_names())

    readline.set_completer_delims(' \t\n;')
    readline.parse_and_bind("tab: complete")
    readline.set_completer(path_complete)
    contract_path = raw_input('Smart-contract path: ')
    contract_alias = prompt('Smart-contract alias: ')
    source_account = prompt('Source account: ', completer=account_completer)
    transfer_qty = prompt('Transfer qty: ')

    contract_filename = ntpath.basename(contract_path)
    exec_command(f'~/smartpy-cli/SmartPy.sh compile {contract_path} ./compile/{contract_filename}', shell=True)
    contract_dir = [f.path for f in os.scandir("./compile/" + contract_filename) if f.is_dir()][0]
    contract_code = contract_dir + "/step_000_cont_0_contract.tz"
    init_storage = build_fa2_storage(get_address(source_account),
                                     "ipfs://QmaJEkhFnFQCwZA3uYWZq3LYvHw4s8RQtEc8sjpWQyJAKp")

    cmd = subprocess.Popen(["tezos-client", "originate",
                            "contract", contract_alias,
                            "transferring", str(transfer_qty),
                            "from", get_address(source_account),
                            "running", contract_code,
                            "--init", f'{init_storage}',
                            "--burn-cap", str(10)
                            ],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = cmd.communicate()
    click.echo(out)
    click.echo(err)


def get_tzc_config_entry_by_account_name(tzc_config_file_path, name):
    with open(tzc_config_file_path, 'r') as f:
        data = json.load(f)
        if len(data) > 0:
            for entry in data:
                if name == entry["name"]:
                    return entry
    return


def export_path():
    path = './account.tzc.json'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).touch(exist_ok=True)
    return path


def nft_path():
    path = './nft.tzc.json'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).touch(exist_ok=True)
    return path


@tzc_account.command(name="export")
@option("--account", help="The account name to export_account")
@option("--force", is_flag=True, help="Overwrite the export account if exists")
def export_account(account, force):
    """Export accounts keys"""
    if account is None:
        account_completer = WordCompleter(get_account_names())
        account = prompt('Account to export: ', completer=account_completer)

    tzc_base_dir = get_config()["base_dir"]
    account_entry = {}

    contract = get_tzc_config_entry_by_account_name(f'{tzc_base_dir}/contracts', account)
    if contract:
        account_entry["contract"] = contract

    public_key_hash = get_tzc_config_entry_by_account_name(f'{tzc_base_dir}/public_key_hashs', account)
    if public_key_hash:
        account_entry["public_key_hash"] = public_key_hash

    public_key = get_tzc_config_entry_by_account_name(f'{tzc_base_dir}/public_keys', account)
    if public_key:
        account_entry["public_key"] = public_key

    secret_key = get_tzc_config_entry_by_account_name(f'{tzc_base_dir}/secret_keys', account)
    if secret_key:
        account_entry["secret_key"] = secret_key

    export = {}
    with open(export_path(), 'r+') as f:
        try:
            export = json.load(f)
        except JSONDecodeError:
            pass
        if account in export and not force:
            click.echo("Hmm, the account has already been exported, use --force to overwrite existing account "
                       "export")
            return
        export[account] = account_entry
        f.seek(0)
        json.dump(export, f, indent=4)


@tzc_account.command(name="snap", help="Make a copy of your existing accounts in your tezos-client base directory")
def save_accounts():
    """Create a copy of knwon tezos-client addresses and keys"""
    tzc_base_dir = get_config()["base_dir"]
    timestamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")

    export_path = f'{tzc_base_dir}/{timestamp}'
    os.makedirs(export_path)

    shutil.copyfile(f'{tzc_base_dir}/contracts', f'{export_path}/contracts')
    shutil.copyfile(f'{tzc_base_dir}/public_key_hashs', f'{export_path}/public_key_hashs')
    shutil.copyfile(f'{tzc_base_dir}/public_keys', f'{export_path}/public_keys')
    shutil.copyfile(f'{tzc_base_dir}/secret_keys', f'{export_path}/secret_keys')

    click.echo("accounts copied to " + export_path)


def append_account(tzc_config_file_path, entry):
    with open(tzc_config_file_path, 'r') as f:
        data = json.load(f)
        data.append(entry)
        json.dump(data, f, indent=4)
    return


def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)


def exported_account_names():
    accounts = []
    exports = load_json(export_path())
    for account in exports:
        accounts.append(account)
    return accounts


@tzc_account.command(name="import", help="Import a clk tzc account to tezos-client")
@option("--account", help="The account name to import")
@option("--force", is_flag=True, help="Overwrite the account if exists")
def import_account(account, force):
    """Import the specified account in tezos-client"""

    if account is None:
        account_completer = WordCompleter(exported_account_names())
        account = prompt('Account to import: ', completer=account_completer)

    exported_account = None
    exported_accounts = load_json(export_path())
    for exported in exported_accounts:
        if exported == account:
            exported_account = exported_accounts[account]
            break
    if not exported_account:
        return click.echo("No such account")

    force_flag = " --force" if force else ""
    if "contract" in exported_account:
        out, err, code = exec_command(
            f'tezos-client remember contract {account} {exported_account["contract"]["value"]}{force_flag}')
        if code == 1:
            click.echo(err)
            click.echo(" " * 4 + f'The import value {exported_account["contract"]["value"]}')

    if "public_key_hash" in exported_account:
        out, err, code = exec_command(
            f'tezos-client add address {account} {exported_account["public_key_hash"]["value"]}{force_flag}')
        if code == 1:
            click.echo(err)

    if "public_key" in exported_account:
        out, err, code = exec_command(
            f'tezos-client import public key {account} {exported_account["public_key"]["value"]["locator"]}{force_flag}')
        if code == 1:
            click.echo(err)

    if "secret_key" in exported_account:
        out, err, code = exec_command(
            f'tezos-client import secret key {account} {exported_account["secret_key"]["value"]}{force_flag}')
        if code == 1:
            click.echo(err)


@tzc.group(name="michelson")
def michelson():
    """Play with michelson"""


@michelson.command(name='mint-nft')
@argument('owner-name', help='The nft owner account name')
@argument('nft-tzc-name', help='The tzc nft name to encode')
@argument('token-id', help='The token_id')
def michelson_mint_nft(owner_name, nft_tzc_name, token_id):
    """Generate the mint michelson parameter"""
    nfts = load_json('./nft.tzc.json')
    if nft_tzc_name in nfts.keys():
        nft = nfts[nft_tzc_name]
    else:
        raise Exception("No such nft ", owner_name, ", you can try one of ", nfts.keys())
    elements = []

    for attr in nft:
        hexValue = hexencode(nft[attr])
        elements.append(f'Elt "{attr}" {hexValue}')

    #  (pair (map %metadata string bytes) (nat %token_id)))
    token_info = '(Pair {' + '; '.join(elements) + '} ' + str(token_id) + ')'
    owner_address = get_address(owner_name)
    mint_params = f'(Pair (Pair "{owner_address}" 1) {token_info} )'

    click.echo(mint_params)
    return mint_params


def get_contracts_names():
    tzc_base_dir = get_config()["base_dir"]
    contracts = load_json(tzc_base_dir + '/contracts')
    return [contract["name"] for contract in contracts]


@interactive.command(name='mint-nft')
def interactive_mint_nft():
    """Interactive NFT mint"""
    contract_completer = WordCompleter(get_contracts_names())
    contract = prompt('Contract: ', completer=contract_completer)

    account_completer = WordCompleter(get_account_names())
    admin = prompt('Contract admin: ', completer=account_completer)
    owner = prompt('NFT owner: ', completer=account_completer)

    tzzc_nft_names = load_json('./nft.tzc.json').keys()
    nft_completer = WordCompleter(tzzc_nft_names)
    nft = prompt('NFT name: ', completer=nft_completer)

    token_id = int(prompt('Token Id: '))

    ctx = click.get_current_context()
    args = ctx.invoke(michelson_mint_nft, owner_name=owner, nft_tzc_name=nft, token_id=token_id)

    cmd = subprocess.Popen(["tezos-client", "call", contract,
                            "from", admin,
                            "--entrypoint", "mint",
                            "--arg", args,
                            "--burn-cap", str(0.5)
                            ],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, _ = cmd.communicate()
    click.echo(out)


@interactive.command(name="transfer-nft")
def interactive_nft_transfer():
    """Interactive NFT transfer"""

    contract_completer = WordCompleter(get_contracts_names())
    contract = prompt('Contract: ', completer=contract_completer)

    accounts = get_account_names()
    account_completer = WordCompleter(accounts)
    admin = prompt('Contract admin: ', completer=account_completer)

    yes_no_completer = WordCompleter(['y', 'n'])

    add_transfer = True
    transfers = []
    while add_transfer:
        from_account = prompt('From (account or literal): ', completer=account_completer)
        if from_account in accounts:
            from_account = get_address(from_account)
        to_account = prompt('To (account or literal): ', completer=account_completer)
        if to_account in accounts:
            to_account = get_address(to_account)
        token_id = int(prompt("Token ID: "))
        qty = int(prompt("Quantity: "))

        transfers.append(f'Pair "{from_account}" {{Pair "{to_account}" (Pair {token_id} {qty}) }}')
        add_transfer = prompt('Transfer another (y/n) ?', completer=yes_no_completer) == 'y'

    args = '{' + '; '.join(transfers) + '}'
    LOGGER.info(args)
    cmd = subprocess.Popen(["tezos-client", "call", contract,
                            "from", admin,
                            "--entrypoint", "transfer",
                            "--arg", args,
                            "--burn-cap", str(0.5)
                            ],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = cmd.communicate()
    click.echo(out)
    click.echo(err)

