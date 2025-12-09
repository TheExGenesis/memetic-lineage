# %%
from lib.image_describer import get_image_descriptions

# %%
tweet_ids = [
    "1427628043665879042",  # book
    "1600065172906790912",  # campfire
    "1443196315970670598",  # heart of philosophy
    "1742494880625016921",  # rich
    "1902390613842014380",  # jc4
]

for entry in get_image_descriptions(tweet_ids[0]):
    print(f"[{entry['media_url']}]\n  {entry['description']}\n")

# %%
