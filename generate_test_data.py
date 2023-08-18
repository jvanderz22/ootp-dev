import csv
import random

test_file = "test_file.csv"
# field_names = ["Ovr", "Contact", "Gap", "Power", "Eye", "K"]
field_names = ["Ovr", "Range", "Error", "Arm"]
rows = 30


def generate_test_data():
    with open(test_file, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=field_names)
        writer.writeheader()
        i = 0
        possibleRatings = [20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]
        while i < rows:
            i += 1
            values = random.choices(
                possibleRatings,
                weights=(0.25, 0.25, 0.5, 0.75, 1, 1, 1, 1, 1, 1, 1, 0.6, 0.4),
                k=len(field_names) - 1,
            )
            overall_rating = None
            while overall_rating is None:
                str = f"\n{i}. Rate this player:\n"
                for j, value in enumerate(values):
                    str += f"\n{field_names[j + 1]}: {value}"
                str += "\nRating: "
                try:
                    overall_rating = int(input(str))
                    if overall_rating > 100 or overall_rating < 0:
                        overall_rating = None
                        print("Invalid rating! Rate Again\n\n\n")
                except ValueError:
                    continue

            row = {
                "Ovr": overall_rating,
            }
            for j, value in enumerate(values):
                row[field_names[j + 1]] = value
            writer.writerow(row)


if __name__ == "__main__":
    generate_test_data()
