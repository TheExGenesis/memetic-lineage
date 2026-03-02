"""
Account Explorer - Get all tweets and conversations for a specific account.

Usage:
    python 24_account_explorer.py visakanv
    python 24_account_explorer.py --account-id 123456
    python 24_account_explorer.py visakanv --no-save
"""

import sys
import argparse
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent))

from lib.account_explorer import (
    get_account_conversations,
    save_account_conversations,
    explore_account,
)


def main():
    parser = argparse.ArgumentParser(
        description="Get all tweets and conversations for a Twitter account"
    )
    parser.add_argument(
        "username",
        nargs="?",
        help="Twitter username (without @)",
    )
    parser.add_argument(
        "--account-id",
        type=int,
        help="Account ID (alternative to username)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save output to file",
    )
    parser.add_argument(
        "--no-quotes",
        action="store_true",
        help="Don't include quote tweet relationships",
    )
    parser.add_argument(
        "--depth-up",
        type=int,
        default=20,
        help="How many parent tweets to include (default: 20)",
    )
    parser.add_argument(
        "--depth-down",
        type=int,
        default=10,
        help="How many reply levels to include (default: 10)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: data/accounts/{username}_conversations.txt)",
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=0,
        help="Print first N characters of output (0 = no preview)",
    )

    args = parser.parse_args()

    if not args.username and not args.account_id:
        parser.error("Must provide either username or --account-id")

    # Get conversations
    result = get_account_conversations(
        username=args.username,
        account_id=args.account_id,
        include_quotes=not args.no_quotes,
        depth_up=args.depth_up,
        depth_down=args.depth_down,
    )

    # Save
    if not args.no_save:
        path = save_account_conversations(result, args.output)
        print(f"\nSaved to: {path}")

    # Preview
    if args.preview > 0:
        print(f"\n{'=' * 60}")
        print("PREVIEW:")
        print(f"{'=' * 60}\n")
        print(result.rendered_text[:args.preview])
        if len(result.rendered_text) > args.preview:
            print(f"\n... ({len(result.rendered_text) - args.preview} more characters)")

    return result


if __name__ == "__main__":
    main()
