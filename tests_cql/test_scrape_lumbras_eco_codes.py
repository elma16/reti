import unittest

from scripts.scrape_lumbras_eco_codes import parse_eco_rows


class LumbrasEcoScraperTests(unittest.TestCase):
    def test_parse_lumbras_eco_rows_extracts_extended_codes(self):
        html = """
        <table>
          <thead><tr><th>ECO</th><th>Name</th><th>Move notation</th></tr></thead>
          <tbody>
            <tr><td>A00q</td><td>Polish: 1&#8230;d5</td><td>1.b4 d5 *</td></tr>
            <tr><td>E99</td><td>King&#8217;s Indian</td><td>1.d4 Nf6 *</td></tr>
            <tr><td>AL</td><td>Alekhine&#8217;s Defence</td><td>1. e4 Sf6</td><td>B02-B05</td></tr>
          </tbody>
        </table>
        """

        rows = parse_eco_rows(html, "https://example.test/eco")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].eco, "A00q")
        self.assertEqual(rows[0].eco_base, "A00")
        self.assertEqual(rows[0].eco_group, "A")
        self.assertEqual(rows[0].name, "Polish: 1…d5")
        self.assertEqual(rows[0].moves, "1.b4 d5")
        self.assertEqual(rows[1].eco, "E99")
        self.assertEqual(rows[1].name, "King’s Indian")


if __name__ == "__main__":
    unittest.main()
