"""
This script updates data_files by using SimulationCrafts casc and dbc extractors.
Basically; execute this script once per patch.
"""
import argparse
from genericpath import exists
import json
import logging
import os
import pathlib
import subprocess
import typing

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)

logger.addHandler(ch)


_LOCALES = [
    "en_US",
    "ko_KR",
    "fr_FR",
    "de_DE",
    "zh_CN",
    "es_ES",
    "ru_RU",
    "it_IT",
    "pt_PT",
]

DATA_PATH = "data_files"


def handle_arguments() -> argparse.ArgumentParser:
    """Scan user provided arguments and provide the corresponding argparse ArgumentParser.

    Returns:
        argparse.ArgumentParser: [description]
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-s",
        "--simc",
        nargs="?",
        default=None,
        help="Absolute path to your local SimulationCraft version.",
    )
    parser.add_argument(
        "-o",
        "--output",
        nargs="?",
        default=os.path.join(pathlib.Path(__file__).parent.absolute(), "tmp"),
        help="Absolute path to the save location of DB files.",
    )
    parser.add_argument(
        "-w",
        "--wow",
        nargs="?",
        default=None,
        help="Absolute path to your World of Warcaft installation to get hotfixes. E.g. /games/World\ of\ Warcraft/_beta_",
    )
    parser.add_argument(
        "--no-load",
        action="store_true",
        help="Flag disables download from CDN. Instead only already present local files are used.",
    )
    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="Flag disables exrating from db2 files. Instead only already present local files are used.",
    )
    parser.add_argument(
        "--ptr",
        action="store_true",
        help="Download PTR files",
    )
    parser.add_argument(
        "--beta",
        action="store_true",
        help="Download BETA files",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )
    return parser


def get_python() -> str:
    """Find and return the appropriate commandline input to use Python 3+

    Returns:
        str: Either "python" or "python3"
    """

    def is_python() -> bool:
        output = subprocess.run(["python", "--version"], stdout=subprocess.PIPE)
        return output.stdout.split()[1].startswith(b"3")

    def is_python3() -> bool:
        output = subprocess.run(["python3", "--version"], stdout=subprocess.PIPE)
        return output.stdout.split()[1].startswith(b"3")

    if not (is_python() or is_python3()):
        raise SystemError("Python 3 is required.")

    return "python" if is_python() else "python3"


def casc(args: object) -> None:
    """Download all db2 files of all locales described in _LOCALES.

    Args:
        args (object): [description]

    Raises:
        SystemError: If Python 3+ is not available in commandline neither via 'python' nor 'python3'.
    """
    if args.no_load:
        logger.info("Skipping download")
        return
    logger.info("Downloading files (casc)")

    python = get_python()

    command = [
        python,
        "casc_extract.py",
        "--cdn",
        "-m",
        "batch",
    ]
    if args.ptr:
        command.append("--ptr")
    elif args.beta:
        command.append("--beta")

    for locale in _LOCALES:
        logger.info(locale)

        process = subprocess.Popen(
            command
            + [
                "--locale",
                locale,
                "-o",
                os.path.join(args.output, locale),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.join(args.simc, "casc_extract"),
        )
        while True:
            output = process.stdout.readline()
            if output == b"" and process.poll() is not None:
                break
            if output:
                logger.debug(output.strip().decode("ascii"))
        rc = process.poll()
        if rc != 0:
            logger.error(f"Error occured while loading {locale}.")


def get_compiled_data_path(args: object, locale: str) -> str:
    return os.path.join(args.output, "compiled", locale)


def dbc(args: object, files: typing.List[str]) -> None:
    """Extract and transforms files into JSON format.

    Args:
        args (object): [description]
        files (typing.List[str]): [description]
    """
    if args.no_extract:
        logger.info("Skipping extraction")
        return
    logger.info("Extracting files (dbc)")

    python = get_python()

    wow_version = os.listdir(os.path.join(args.output, _LOCALES[0]))[0]

    command = [
        python,
        "dbc_extract.py",
        "-b",
        wow_version,
        "-t",
        "json",
    ]
    if args.wow:
        command.append("--hotfix")
        command.append(os.path.join(args.wow, "Cache/ADB/enUS/DBCache.bin"))

    for file in files:
        for locale in _LOCALES:
            logger.info(f"{file} {locale}")

            cmd = command + [
                "-p",
                os.path.join(args.output, locale, wow_version, "DBFilesClient"),
                file,
            ]

            logger.debug(cmd)
            pathlib.Path(os.path.join(get_compiled_data_path(args, locale))).mkdir(
                parents=True, exist_ok=True
            )

            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.join(args.simc, "dbc_extract3"),
            )
            if process.returncode != 0:
                logger.error(
                    f"Error occured while extracting {file} {locale}. {process.stderr}"
                )
            else:
                with open(
                    os.path.join(get_compiled_data_path(args, locale), f"{file}.json"),
                    "wb",
                ) as f:
                    f.write(process.stdout)


def update_trinkets(args: object) -> None:
    """Update data_files/trinkets.json

    Args:
        args (object): [description]

    Returns:
        None
    """

    logger.info("Update trinkets")
    # TODO: add ItemEffect to know which trinkets have on use effects
    DB_FILES = ["ItemSparse"]

    WHITELIST = []

    def is_trinket(item: dict) -> bool:
        """See https://github.com/simulationcraft/simc/blob/shadowlands/engine/dbc/data_enums.hh#L335"""
        return item.get("inv_type") == 12

    def is_gte_rare(item: dict) -> bool:
        """See https://github.com/simulationcraft/simc/blob/shadowlands/engine/dbc/data_enums.hh#L369"""
        return item.get("quality") >= 3

    def is_shadowlands(item: dict) -> bool:
        """Tests for itemlevel and chracter level requirement."""
        # unbound changeling is somehow available for lvl 1
        return is_gte_ilevel(item)  # and is_gte_level(item)

    def is_gte_level(item: dict) -> bool:
        """An Expansion starts at the last possible character level of the previous one."""
        return item.get("req_level") >= 50

    def is_gte_ilevel(item: dict) -> bool:
        """Value of normal Dungeon items at level 50."""
        return item.get("ilevel") >= 155

    def is_whitelisted(item: dict) -> bool:
        return item.get("id") in WHITELIST or item.get("name") in WHITELIST

    dbc(args, DB_FILES)

    data = {}

    for locale in _LOCALES:
        with open(
            os.path.join(get_compiled_data_path(args, locale), f"{DB_FILES[0]}.json"),
            "r",
        ) as f:
            items = json.load(f)

        data[locale] = [
            item
            for item in items
            if is_trinket(item)
            and is_gte_rare(item)
            and is_shadowlands(item)
            or is_whitelisted(item)
        ]

    trinkets = []
    # TODO: research fields and possibly remove more
    item_keys = [
        "id",
        "race_mask",
        "desc",
        "name",
        "duration",
        "bag_family",
        "ranged_mod_range",
        "ilevel",
        "class_mask",
        "id_expansion",
        "req_level",
        "inv_type",
        "quality",
        "translations",
    ]
    for i in range(1, 11):
        item_keys.append(f"stat_alloc_{i}")
        item_keys.append(f"stat_type_{i}")

    for i, locale in enumerate(_LOCALES):
        # prepare
        if i == 0:
            item: dict
            for item in data[locale]:
                item["translations"] = {locale: item["name"]}
                new_item = {}
                for key in item_keys:
                    new_item[key] = item[key]
                trinkets.append(item)

        # enrich
        else:
            for item in data[locale]:
                for trinket in trinkets:
                    if trinket["id"] == item["id"]:
                        trinket["translations"][locale] = item["name"]

    logger.debug(f"Count: {len(trinkets)}")

    with open(os.path.join(DATA_PATH, "trinkets.json"), "w") as f:
        json.dump(trinkets, f, ensure_ascii=False)


def main() -> None:
    args = handle_arguments().parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)
    casc(args)
    update_trinkets(args)


if __name__ == "__main__":
    main()
