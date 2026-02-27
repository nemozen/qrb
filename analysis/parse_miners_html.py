#!/usr/bin/python3
'''Take table from https://hashrateindex.com/rigs and print out as
CSV which can be appended to miners.csv

The input to this script is an element that looks like:
<div data-cy="CompositeTable-table-mobile-responsive">...</div>
Every 14 elements correspond to a table row with 7 (value, name) pairs.

'''
import sys
from html.parser import HTMLParser


row_element_mapping = {
    1: "Name",
    2: "Date",
    3: "Hashrate",
    4: "Watts",
    5: "Efficiency"
}


class MinersTableParser(HTMLParser):
    _rowelement = 0
    _row_dict = {}

    def handle_data(self, data):
        self._rowelement += 1
        if self._rowelement in row_element_mapping.keys():
            col_name = row_element_mapping[self._rowelement]
            self._row_dict[col_name] = data
        if self._rowelement == 8:
            efficiency = self._row_dict["Efficiency"].split(" ")[0]  # XX W/TH
            hashrate = self._row_dict["Hashrate"].split(" ")[0]  # XXX TH/s
            power = self._row_dict["Watts"].split(" ")[0]  # XXX W
            self._row_dict["Hashrate"] = "{}Th/s".format(hashrate)
            self._row_dict["Power"] = "{}W".format(power)
            self._row_dict["Noise"] = ""
            self._row_dict["Algorithm"] = ""
            print(",".join(
                [self._row_dict[col] for col in [
                    "Name", "Date", "Hashrate", "Power", "Noise", "Algorithm"]]))
            self._rowelement=0
            self._row_dict = {}


parser = MinersTableParser()
for line in open(sys.argv[1]):
    parser.feed(line)
