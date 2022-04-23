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
import rich
from clk.decorators import group
from clk.decorators import option
from clk.lib import call, check_output, safe_check_output, read, json_dump_file
from clk.log import get_logger
from distlib.compat import raw_input
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.validation import Validator
from rich import print_json
from rich.panel import Panel
from rich.pretty import Pretty
from rich.progress import Progress
from rich.table import Table

LOGGER = get_logger(__name__)


class SmartPyCli:
    clk_install_script_path = str(Path.home()) + '/.config/clk/extensions/tezos_client/install-smartpy.sh'
    base_dir = str(Path.home()) + '/smartpy-cli/'
    script_path = base_dir + 'SmartPy.sh'


class TezosClient:
    clk_install_script_path = str(Path.home()) + '/.config/clk/extensions/tezos_client/install-tezos-client.sh'
    base_dir = str(Path.home()) + '/.tezos-client/'
    config_path = base_dir + 'config'
    contracts_path = base_dir + 'contracts'
    secret_keys_path = base_dir + 'secret_keys'
    public_keys_hashs_path = base_dir + 'public_key_hashs'
    public_keys_path = base_dir + 'public_keys'
    rpcs = ['https://hangzhounet.api.tez.ie', 'https://ithacanet.ecadinfra.com', 'https://hangzhounet.smartpy.io/',
            'https://ithacanet.smartpy.io/']


class Tzc:
    nft_path = './nft.tzc.json'
    export_path = './account.tzc.json'


def safe_json_read_array(path):
    r = read(path)
    if r:
        return json.loads(r)
    else:
        LOGGER.debug(f"No content for path={path}, returning empty array in place")
        return []


def safe_json_read_object(path):
    try:
        r = read(path)
    except OSError:
        r = None
    if r:
        return json.loads(r)
    else:
        LOGGER.debug(f"No content for path={path}, returning empty object in place")
        return {}


def echo_list(elems, **kwargs):
    res = sorted(elems, key=kwargs['sort_key']) if 'sort_key' in kwargs else elems
    res = '\n'.join(list(map(kwargs['formatter'], res))) if 'formatter' in kwargs else res
    click.echo(res)


def echo_obj(elems, **kwargs):
    res = '\n'.join(list(map(kwargs['formatter'], elems.items()))) if 'formatter' in kwargs else elems
    click.echo(res)


def stream_command(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    while True:
        output = process.stdout.readline()
        if not output and process.poll() is not None:
            break
        if output:
            rich.print(output.decode("utf-8").rstrip())
    rc = process.poll()

    if rc:
        rich.print(Panel(":no_entry: "
                         + f"{' '.join(command)} :\n\n{process.stderr.read().decode('utf-8')}"))
    else:
        rich.print(Panel('[bold green]:heavy_check_mark: [/bold green] ' + ' '.join(command)))

    return rc


def validator(valids, error='Not a valid value'):
    return Validator.from_callable(
        lambda x: x in valids,
        error_message=error,
        move_cursor_to_end=True)


def tzc_prompt(msg, choices):
    return prompt(msg,
                  completer=WordCompleter(choices),
                  validator=validator(choices),
                  mouse_support=True
                  )


@group()
def tzc():
    """Commands to play with tezos-client

    While playing with the tezos block chain, this command aims to make it easier to use the underlying tezos-client command.
    See:
    \t- Tezos - https://tezos.com \r
    \t- https://tezos.gitlab.io/shell/cli-commands.html
    """


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


def echo_invalid(msg):
    rich.print("[bold red] :no_entry: [/bold red]" + msg)


@tzc.command()
@option('--rpc', help='The Tezos RPC node to connect')
def install(rpc):
    """Install required dependencies such as tezos-client and smartpy-cli"""

    def beautifier(x):
        rich.print('[bold green]:heavy_check_mark: [/bold green] ' + x)

    with Progress(transient=True) as progress:
        def progress_setup(f):
            progress.stop()
            f()
            progress.start()

        task1 = progress.add_task("[green]npm...", total=4)

        npm_version = safe_check_output(['npm', '--version'])
        if npm_version:
            beautifier(f"npm {npm_version.strip()}")
        else:
            progress_setup(lambda: call(split('sudo apt install nodejs npm')))

        progress.update(task1, advance=1, description="[green]smartpy-cli ...")
        smpy_version = client_version()
        if smpy_version:
            beautifier(f'smartpy-cli {smpy_version.strip()}')
        else:
            progress_setup(install_smartpy_cli)
        progress.update(task1, advance=1, description="[green]tezos-client ...")

        tzc_version = safe_check_output(['tezos-client', '--version'])
        if tzc_version:
            beautifier(f'tezos-clients {tzc_version.strip()}')
        else:
            progress_setup(install_tezos_client)
        progress.update(task1, advance=1, description="[green]Configuring tezos-client endpoint ...")

        config = safe_json_read_object(TezosClient.config_path)
        if config and config['endpoint']:
            beautifier(f'tezos-client endpoint: {config["endpoint"]}')
        else:
            if not rpc:
                progress.stop()
                rich.print(':magnifying_glass_tilted_right: https://tezostaquito.io/docs/rpc_nodes/')
                rpc = prompt('RPC address : ', completer=WordCompleter(TezosClient.rpcs))
                progress.start()
            click.get_current_context().invoke(network_set, rpc_link=rpc)
        progress.update(task1, advance=1)


def get_account_names():
    contracts = safe_json_read_array(TezosClient.public_keys_hashs_path)
    return list(map(lambda x: x['name'], contracts))


def find_first_account_by_name(name):
    contracts = safe_json_read_array(TezosClient.public_keys_hashs_path)
    return next(filter(lambda x: x['name'] == name, contracts))


@tzc.group(name="account")
def account():
    """Play with accounts"""


@account.command(name="export")
@option("--account", help="The account name to export")
@option("--verbose", is_flag=True, help="The account name to export")
@option("--force", is_flag=True, help="Overwrite the export account if exists")
def account_export(account, verbose, force):
    """Export accounts keys"""

    accounts = safe_json_read_array(TezosClient.public_keys_path)
    names = list(map(lambda x: x['name'], accounts))
    if verbose:
        click.get_current_context().invoke(account_show)
    if not account or account not in names:
        account = prompt("Alias to export >",
                         completer=WordCompleter(names),
                         validator=validator(names, 'Not a valid alias'),
                         mouse_support=True)

    account_entry = {}

    contract = get_tzc_config_entry_by_account_name(TezosClient.contracts_path, account)
    if contract:
        account_entry["contract"] = contract

    public_key_hash = get_tzc_config_entry_by_account_name(TezosClient.public_keys_hashs_path, account)
    if public_key_hash:
        account_entry["public_key_hash"] = public_key_hash

    public_key = get_tzc_config_entry_by_account_name(TezosClient.public_keys_path, account)
    if public_key:
        account_entry["public_key"] = public_key

    secret_key = get_tzc_config_entry_by_account_name(TezosClient.secret_keys_path, account)
    if secret_key:
        account_entry["secret_key"] = secret_key

    export = {}
    with open(Tzc.export_path, 'r+') as f:
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


@account.command(name="import", help="Import a clk tzc account to tezos-client")
@option("--alias", help="The account alias to import")
@option("--verbose", is_flag=True, help="Show available accounts")
@option("--force", is_flag=True, help="Overwrite the account if exists")
def account_import(alias, verbose, force):
    """Import the specified account in tezos-client"""

    exports = safe_json_read_object(Tzc.export_path)
    names = list(exports.keys())
    if verbose:
        table = Table(title="Known exports")
        table.add_column("Alias", justify="right")
        for name in names:
            table.add_row(name)
        rich.print(table)

    if alias not in exports:
        alias = prompt('Account to import > ',
                       completer=WordCompleter(names),
                       validator=validator(exports),
                       mouse_support=True)
    account = exports[alias]
    force_flag = " --force" if force else ""
    with Progress(transient=True) as progress:
        def progress_setup(f):
            progress.stop()
            f()
            progress.start()

        task1 = progress.add_task("[green]contract...", total=3)

        if "contract" in account:
            stream_command(split(
                f'tezos-client remember contract {alias} {account["contract"]["value"]}{force_flag}'))

        progress.update(task1, advance=1, description="[green]public_key_hash ...")
        if "public_key_hash" in account:
            stream_command(split(
                f'tezos-client add address {alias} {account["public_key_hash"]["value"]}{force_flag}'))

        progress.update(task1, advance=1, description="[green]public_key ...")
        if "public_key" in account:
            stream_command(split(
                f'tezos-client import public key {alias} {account["public_key"]["value"]["locator"]}{force_flag}'))

        progress.update(task1, advance=1, description="[green]secret_key ...")
        if "secret_key" in account:
            stream_command(split(
                f'tezos-client import secret key {alias} {account["secret_key"]["value"]}{force_flag}'))


@account.command(name="show")
def account_show():
    """List configured accounts usable by the client."""
    accounts = safe_json_read_array(TezosClient.public_keys_hashs_path)

    table = Table(title="Known accounts")
    table.add_column("Alias", justify="right")
    table.add_column("Address", justify="left")
    for a in accounts:
        table.add_row(a['name'], a['value'])
    if table.rows:
        rich.print(table)
    else:
        rich.print(f":person_shrugging: [i]No accounts [/i]")


@account.command(name="snap", help="Make a copy of your existing accounts in your tezos-client base directory")
def account_snap():
    """Create a copy of knwon tezos-client addresses and keys"""
    tzc_base_dir = TezosClient.base_dir
    timestamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")

    export_path = os.path.join(tzc_base_dir, timestamp)
    os.makedirs(export_path)

    def snap_copy(name):
        shutil.copyfile(os.path.join(tzc_base_dir, name),
                        os.path.join(export_path, name))

    snap_copy('contracts')
    snap_copy('public_key_hashs')
    snap_copy('public_keys')
    snap_copy('secret_keys')

    rich.print("[bold green] :heavy_check_mark: [/bold green] accounts copied to " + export_path)


@tzc.group(name="network")
def network():
    """Configure tezos-client"""


@network.command(name="set")
@option("--rpc-link", envvar='RPC_LINK', help="RPC tezos node address")
def network_set(rpc_link):
    """Set the RPC tezos node address"""
    if not rpc_link:
        rpc_link = prompt("RPC Link > ", completer=WordCompleter(TezosClient.rpcs))

    LOGGER.status(f'Configuring tezos-client network with {rpc_link}')
    call(["tezos-client", "--endpoint", rpc_link, "config", "update"], stderr=subprocess.DEVNULL)
    LOGGER.info(f'Result:')
    call(["tezos-client", "config", "show"], stderr=subprocess.DEVNULL)


@network.command(name="show")
def network_show():
    """Show tezos-client node configuration."""
    config = safe_json_read_object(TezosClient.config_path)
    if "endpoint" in config:
        endpoint = config["endpoint"]
        click.echo(endpoint)
        print_json(check_output(['curl', os.path.join(endpoint, 'version'), '-s']))


@account.command(name="transfer")
@option('--source', help='The account alias from which the XTZ will be taken')
@option('--dest', help='The account alias or address to which the XTZ will sent')
@option('--amount', help='The XTZ amount to sent')
def account_transfer(source, dest, amount):
    """XTZ transfer"""
    account_names = get_account_names()
    if source and source not in account_names:
        echo_invalid(f"Invalid source={source}")
        source = None
    if amount and not amount.isnumeric():
        echo_invalid(f"Invalid amount={amount}")
        amount = None
    if not source:
        source = tzc_prompt('From account > ', account_names)

    if not amount:
        amount = prompt('XTZ Amount > ')

    if not dest:
        dest = prompt('To (account name or address): ', completer=WordCompleter(account_names))

    stream_command(["tezos-client",
                    "transfer", amount,
                    "from", source,
                    "to", dest,
                    "--burn-cap", "0.5"])


def path_complete(text, state):
    return (glob.glob(text + '*') + [None])[state]


def hexencode(str):
    res = str.encode('utf-8').hex()
    return "0x" + res


def build_fa2_storage(admin_address, metadata):
    res = '(Pair ' \
          '(Pair (Pair "' + admin_address + '" 0) '  # admin
    res += '(Pair {} '  # ledger
    res += '(Pair {Elt "" ' + hexencode(metadata) + ' }'  # metadata
    res += '{}))) '  # operator
    res += '(Pair (Pair {} '  # (pair (big_map %owner_by_token_id nat address)
    res += '(Pair {} False))'  # (bool %paused)
    res += ' (Pair {} (Pair {} {}))))'  # %token_metadata %token_info %total_supply
    return res


def get_tzc_config_entry_by_account_name(tzc_config_file_path, name):
    with open(tzc_config_file_path, 'r') as f:
        data = json.load(f)
        if len(data) > 0:
            for entry in data:
                if name == entry["name"]:
                    return entry
    return


def michelson_mint_nft_paramaters(owner_name, nft_tzc_name, token_id):
    """Generate the mint michelson parameter"""
    nfts = safe_json_read_object('./nft.tzc.json')
    if nft_tzc_name in nfts.keys():
        nft = nfts[nft_tzc_name]
    else:
        raise Exception("No such nft ", nft_tzc_name, ", you can try one of ", nfts.keys())
    elements = []

    for attr in nft:
        hexValue = hexencode(nft[attr])
        elements.append(f'Elt "{attr}" {hexValue}')

    #  (pair (map %metadata string bytes) (nat %token_id)))
    token_info = '(Pair {' + '; '.join(elements) + '} ' + str(token_id) + ')'
    owner_address = find_first_account_by_name(owner_name)['value']
    mint_params = f'(Pair (Pair "{owner_address}" 1) {token_info} )'

    return mint_params


@tzc.group(name="contract")
def contract():
    """Play with contracts"""


def get_contract_names():
    contracts = safe_json_read_array(TezosClient.contracts_path)
    return list(map(lambda x: x['name'], contracts))


@contract.command(name="show")
@option("--alias", help="Show the contract address for the given alias")
def contract_show(alias):
    """List known contracts alias and address"""

    contracts = safe_json_read_array(TezosClient.contracts_path)

    if alias:
        c = next((x for x in contracts if x['name'] == alias))
        if c:
            return click.echo(c['value'])
    table = Table(title="Known contracts")
    table.add_column("Alias", justify="right")
    table.add_column("Address", justify="left")
    for c in contracts:
        table.add_row(c['name'], c['value'])
    if table.rows:
        rich.print(table)
    else:
        rich.print(f":person_shrugging: [i]No accounts [/i]")


@contract.command(name="add")
@option("--alias", help="The alias of the contract")
@option("--address", help="The address of the contract")
@option("--force", is_flag=True, help="Force the import if exists")
def contract_add(alias, address, force):
    """Add a contract alias for the given address"""
    if not alias:
        alias = prompt("Alias >")
    if not address:
        address = prompt("Address >")

    force = '--force' if force else ''
    stream_command(split(f'tezos-client remember contract {alias} {address}{force}'))


@contract.command(name="remove")
@option("--alias", help="The alias of the contract")
@option("--verbose", is_flag=True, help="Print the available values")
def contract_remove(alias, verbose):
    """Remove a contract alias"""
    contracts = safe_json_read_array(TezosClient.contracts_path)
    names = list(map(lambda x: x['name'], contracts))

    if not alias:
        alias = ''

    if not alias or alias not in names:
        if verbose:
            ctx = click.get_current_context()
            ctx.invoke(contract_show)
        alias = prompt("Alias to remove >",
                       default=alias,
                       completer=WordCompleter(names),
                       validator=validator(names, 'Not a valid alias'),
                       mouse_support=True)

    json_dump_file(TezosClient.contracts_path, list(filter(lambda x: x['name'] != alias, contracts)))


# TODO options
@contract.command(name="deploy-fa2")
@option('--force', is_flag=True, help='Overwrite alias if already exists')
def contract_fa2_deploy(force):
    """FA2 contract deployment"""
    accounts = safe_json_read_array(TezosClient.public_keys_hashs_path)
    account_names = list(map(lambda x: x['name'], accounts))

    readline.set_completer_delims(' \t\n;')
    readline.parse_and_bind("tab: complete")
    readline.set_completer(path_complete)
    contract_path = raw_input('Smart-contract path > ')

    contract_alias = prompt('Give an alias to this contract > ')
    source_account = tzc_prompt('Admin > ', account_names)
    transfer_qty = 0

    contract_filename = ntpath.basename(contract_path)
    call([SmartPyCli.script_path, 'compile', contract_path, f'./compile/{contract_filename}'])
    contract_dir = [f.path for f in os.scandir("./compile/" + contract_filename) if f.is_dir()][0]
    contract_code = contract_dir + "/step_000_cont_0_contract.tz"
    # FIXME hard coded IPFS
    init_storage = build_fa2_storage(find_first_account_by_name(source_account)['value'],
                                     "ipfs://QmaJEkhFnFQCwZA3uYWZq3LYvHw4s8RQtEc8sjpWQyJAKp")

    command = ["tezos-client", "originate",
               "contract", contract_alias,
               "transferring", str(transfer_qty),
               "from", find_first_account_by_name(source_account)['value'],
               "running", contract_code,
               "--init", f'{init_storage}',
               "--burn-cap", str(10)
               ]
    if force:
        command.append('--force')
    stream_command(command)


@tzc.group()
def nft():
    """Play with NFT"""


@nft.command(name='mint')
@option('--contract', help='The smart-contract alias that will own the NFT')
@option('--admin', help='The smart-contract account alias')
@option('--owner', help='The account that will own the NFT')
@option('--nft-alias', help='The NFT alias to mint')
@option('--token-id', help='The NFT token id')
def nft_mint(contract, admin, owner, nft_alias, token_id):
    """Mint NFT for a given contract"""
    contract_names = get_contract_names()
    if contract and contract not in contract_names:
        echo_invalid(f'Unknown contract={contract}')
        contract = None

    account_names = get_account_names()
    if admin and admin not in account_names:
        echo_invalid(f'Unknown admin={admin}')
        admin = None

    nft_names = safe_json_read_object('./nft.tzc.json').keys()
    if nft_alias and nft_alias not in nft_names:
        echo_invalid(f'Unknown nft alias={nft_alias}')
        nft_alias = None

    if not contract:
        contract = tzc_prompt('Contract > ', contract_names)
    if not admin:
        admin = tzc_prompt('Contract admin > ', account_names)
    if not owner:
        # TODO Allow to provide a literal or an alias
        owner = tzc_prompt('NFT owner > ', get_account_names())
    if not nft_alias:
        nft_alias = tzc_prompt('NFT name > ', list(nft_names))

    if not token_id:
        token_id = int(prompt('Token Id: '))

    args = michelson_mint_nft_paramaters(owner, nft_alias, token_id)

    stream_command(["tezos-client", "call", contract,
                    "from", admin,
                    "--entrypoint", "mint",
                    "--arg", args,
                    "--burn-cap", str(0.5)
                    ])


@nft.command(name='transfer')
@option('--contract', help='The contract owning the NFT')
@option('--contract-admin', help='The admin of the contract')
@option('--prev-owner', help='The previous nft owner account address')
@option('--next-owner', help='The next nft owner account address')
@option('--token-id', help='The nft token id')
def nft_transfer(contract, contract_admin, prev_owner, next_owner, token_id):
    """Transfer nft"""
    contract_names = get_contract_names()
    if contract and contract not in contract_names:
        echo_invalid(f"Not a valid contract={contract}")
        contract = None

    account_names = get_account_names()
    if contract_admin and contract_admin not in account_names:
        echo_invalid(f"Not a valid admin={contract_admin}")
        contract_admin = None

    if not contract_admin:
        contract_admin = tzc_prompt('Contract admin > ', account_names)
        contract_admin = find_first_account_by_name(contract_admin)['value']
    if not contract:
        contract = tzc_prompt('Contract > ', contract_names)

    yes_no_completer = WordCompleter(['y', 'n'])

    transfers = []
    if prev_owner and next_owner and token_id:
        # TODO Handle alias
        transfers.append(f'Pair "{prev_owner}" {{Pair "{next_owner}" (Pair {token_id} 1) }}')
    else:
        add_transfer = True
        while add_transfer:
            from_account = prompt('From (account or literal): ', completer=WordCompleter(account_names))
            if from_account in account_names:
                from_account = find_first_account_by_name(from_account)['value']

            to_account = prompt('To (account or literal): ', completer=WordCompleter(account_names))
            if to_account in account_names:
                to_account = find_first_account_by_name(to_account)['value']
            token_id = int(prompt("Token ID: "))

            qty = int(prompt("Quantity: ", default='1'))
            transfers.append(f'Pair "{from_account}" {{Pair "{to_account}" (Pair {token_id} {qty}) }}')
            add_transfer = prompt('Transfer another (y/n) ?', completer=yes_no_completer) == 'y'

    args = '{' + '; '.join(transfers) + '}'
    stream_command(["tezos-client",
                    "call", contract,
                    "from", contract_admin,
                    "--entrypoint", "transfer",
                    "--arg", args,
                    "--burn-cap", str(0.5)
                    ])


@nft.command(name='show')
def nft_show():
    """Show the known TZC nft templates"""
    nfts = safe_json_read_object(Tzc.nft_path)
    table = Table(title="Known NFTs")
    table.add_column("Alias", justify="right")
    table.add_column("Metadata", justify="left")

    for name in nfts:
        table.add_row(name, Pretty(nfts[name]))
    if table.rows:
        rich.print(table)
    else:
        rich.print(f":person_shrugging: [i]No NFTs found at {Tzc.nft_path}[/i]")
