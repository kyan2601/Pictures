from src import automation


def main():
    year = 2023
    automation.index_metadata_for_year(year)

    # mf = MetadataFile.get_instance(year)
    # mf.df['width'] = mf.df['width'].astype(int)
    # mf.df['height'] = mf.df['height'].astype(int)
    # mf.write()


if __name__ == '__main__':
    main()
