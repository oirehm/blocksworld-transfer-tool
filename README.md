# Blocksworld Transfer Tool (BTT)

Moves your [Blocksworld](https://store.steampowered.com/app/642390/Blocksworld/) worlds and models from one account folder to another, even across different builds of the game.

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/oirehm/blocksworld-transfer-tool/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Requirements

- [Python](https://www.python.org/downloads/) 3.8 or newer. When installing on Windows, tick "Add python.exe to PATH"
- Only tested on Windows 11

## Installation

Download `transfer.py` from the [latest release](https://github.com/oirehm/blocksworld-transfer-tool/releases), or clone the repository:

```
git clone https://github.com/oirehm/blocksworld-transfer-tool.git
```

## Usage

Make sure Blocksworld is closed, then run `transfer.py`:

```
python transfer.py
```

It finds your accounts and asks which one to transfer into, then which one has the data to be transferred. Type `b` at either question to browse for a folder instead, or pass both paths yourself. Each can be an account folder (shown below) or a single `worlds` or `models` folder, and the one you copy from can also be a single world or model folder:

```
python transfer.py "C:\path\to\copy\from" "C:\path\to\copy\into"
```

The game keeps your worlds and models here, one folder per account. The original game (BW1) and the community version (BW2) name the folder after your Steam id, the playtest after your account id:

```
BW1        %USERPROFILE%\Documents\Blocksworld\user_<steam id>\
BW2        %USERPROFILE%\Documents\blocksworld_develop\user_<steam id>\
Playtest   %USERPROFILE%\AppData\LocalLow\Fortell Games\Blocksworld\blocksworld_develop\<account id>\
```

If your Documents folder lives in OneDrive, the first two start with `%USERPROFILE%\OneDrive` instead.

The destination account needs at least one saved world to receive worlds, and one saved model to receive models, because the tool copies how the game lays out its files from an existing one.

## Data Handling

BTT is a local tool and does not connect to the internet. The tool checks a fixed list of folders where the game keeps its library, under your user folder, and only reads and writes in your BW folders.

## FAQ

**Can this break my worlds/models?**

No. The account you copy from is only read from. Each world or model is written as a new folder in the destination account. There is nothing this tool can do to delete existing data.

**How do I undo a transfer?**

If you have not started the game since the transfer, just delete the transferred folders. Once the game has seen it, delete the world inside the game instead, as it is saved on the server and comes back if you only delete the files.

**Does it work with the original game, iOS data, and the playtest?**

Yes. The file format has not changed since 2013 (as of 2026), so any build's worlds can open in any other, and transfers work in both directions, including moving playtest worlds back into the original game, though blocks or tiles the playtest added since will not exist there. iOS worlds work too once the folder is copied off the phone.

**Someone sent me a world/model. How do I transfer only that?**

Type `b` or `browse` at the second question asking which account has the data, and select the world/model folder. Or pass the folder as the first path when run via terminal.

**A world I already transferred is offered again. Why?**

You edited the transferred copy in the destination account. The tool sees different blocks and cannot tell the two apart, so it lists the original as new again. Answer `n`, or `y` to get the untouched original alongside your edited one.

**I only see one account.**

The other game has never saved a world or model on this computer, so there is nothing to find yet. Start it, save one, and run this again.

**It says the destination is empty.**

The tool copies how the game lays out its files from an existing world or model, so save one world (to receive worlds) or one model (to receive models) in that game first.

**It says Blocksworld is running, but I closed it.**

Check Task Manager for a leftover `Blocksworld.exe` and close it.

## Issues & Contributing

Every run is recorded in `transfer.log` next to the script. Please [open an issue](https://github.com/oirehm/blocksworld-transfer-tool/issues) with the log attached if you encounter any bugs. Pull requests are welcome.

## Credits

Inspired by zenith391's Blocksworld World Editor (BWWE)

## License

[MIT License](LICENSE)

## Disclaimer

[Blocksworld](https://store.steampowered.com/app/642390/Blocksworld/) is a 2013 block-building sandbox by [Linden Lab](https://www.lindenlab.com/) where you can program your creations, now being revived by [Fortell Games](https://fortell.games/games/blocksworld). This tool is not affiliated with or endorsed by Linden Lab or Fortell Games.

## Contact

[oirehmiockn@gmail.com](mailto:oirehmiockn@gmail.com)
