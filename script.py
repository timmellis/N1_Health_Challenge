import sqlite3
import pandas as pd

connection = sqlite3.connect("interview.db")
cur = connection.cursor()
firstIndexCur = connection.cursor()
firstIndexCur.row_factory = lambda cursor, row: row[0]


###############################################
### SECTION 0:                              ###
### - CREATE NEW TABLE (IF NOT EXISTS),     ###
### - IMPORT AGGREGATE DATA                 ###

stdMemberCols = ("member_id INT,"
                "member_first_name CHAR,"
                "member_last_name CHAR,"
                "date_of_birth DATE,"
                "main_address VARCHAR(500),"
                "city CHAR,"
                "state CHAR,"
                "zip_code INT,"
                "payer CHAR")

cur.execute("CREATE TABLE IF NOT EXISTS std_member_info ("+ stdMemberCols +")")

# ----------------------------------------------------
### CREATE FUNCTION TO:                            ###
### IMPORT DATA TO NEW TABLE BY ELIGIBILITY MONTH, ###
### UPDATE NON-STANDARD DATE FORMATTING            ###

def import_data():
  allrosters = []

  allrosters = firstIndexCur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%roster%' ORDER BY name").fetchall()

  for roster in allrosters:

    thiscur = connection.cursor()
    
    # -----------------------------------------------------------------
    ### UPDATE DATE FORMATTING IF 'mm/dd/YYYY' INSTEAD OF 'YYYY-mm-DD':

    test_dateformat = firstIndexCur.execute("SELECT eligibility_start_date FROM " + roster).fetchone()

    if "/" in test_dateformat:
      print("ERROR: WRONG DATE FORMAT", roster, test_dateformat )

      # # Looked up a lot of help documentation, this method didn't work #
      # thiscur.execute("SELECT eligibility_start_date,STRFTIME('%Y-%m-%d', eligibility_start_date) AS formatted FROM " + roster).fetchone()
      
      data = thiscur.execute("SELECT eligibility_start_date,eligibility_end_date,Person_Id FROM %s" % (roster)).fetchall()
      
      # Manually split date string, recontstruct in proper format:
      for t in data:
        start_split, end_split = t[0].split("/"), t[1].split("/")
        newstart = "%s-%s-%s" % (start_split[2], start_split[0], start_split[1])
        newend = "%s-%s-%s" % (end_split[2], end_split[0], end_split[1])

        # Update [roster] with new date formats:
        sql = ("UPDATE %s SET eligibility_start_date = '%s', eligibility_end_date = '%s' WHERE Person_Id = '%s'" % (roster, newstart, newend, t[2]))
        
        thiscur.execute(sql)
        connection.commit()

    ### (END UPDATE DATE FORMAT)
    # ----------------------------------------
    ### IMPORT AGGREGATE DATA FROM EACH ROSTER:

    # For each [roster], create string of requested columns for SQL queries: 
    reqdCols = ("Person_Id,"
                "First_Name,"
                "Last_Name,"
                "Dob,"
                "Street_Address,"
                "City,"
                "State,"
                "Zip,"
                "payer")

    # SELECT all required columns from each ROSTER where eligibility must include 2022-04-01
    data = thiscur.execute( "SELECT %s FROM %s WHERE eligibility_start_date<='2022-04-01' AND eligibility_end_date>'2022-04-01'" % (reqdCols, roster)).fetchall()

    # INSERT all records from [roster] into STD_MEMBER_INFO table
    thiscur.executemany("INSERT INTO std_member_info VALUES(?,?,?,?,?,?,?,?,?)", data)
    connection.commit()

# END def import_data()

# ----------------------------------------------
# ### RUN THE FUNCTION ONCE at start of analysis. 
# ### (NOTE: Comment out during debugging so as not to reimport data and clog analysis table)

# import_data()

### END SECTION 0 ###
#####################


################################
### SECTION 1:               ###
### SUMMARY OF IMPORTED DATA ###

print("""
*****************************
*** IMPORTED DATA SUMMARY *** """)


# --------------------------------------------------------------
### CHECK FOR DISTINCT MEMBERS, HOW MANY MEMBERS ARE DUPLICATES:

members_all_count = firstIndexCur.execute("SELECT count(*) FROM std_member_info").fetchone()
members_distinct = cur.execute("SELECT DISTINCT member_id FROM std_member_info").fetchall()
duplicate_entries = members_all_count - len(members_distinct)

print("There are %s entries for members eligible in April, 2022. This includes:" % members_all_count) 
print("--- %s distinct members." % len(members_distinct))
print("--- %s duplicate entries." % (duplicate_entries))


# -------------------------
### SORT BY "PAYER" COLUMN:

payersql = "SELECT payer,COUNT(DISTINCT member_id) AS members FROM std_member_info GROUP BY payer"
# sortbypayer = cur.execute(payersql).fetchall()
payer_dataframe = pd.read_sql_query(payersql, connection)                                     # Create a Pandas dataframe to format data
payer_dataframe['pct (%)'] = round(payer_dataframe.members / len(members_distinct) * 100,2)   # Add a 'Percentage' column to dataframe

print("""
**************************
*** BREAKDOWN BY PAYER ***""")

print(payer_dataframe)

# ### Removed, replaced by Pandas dataframe (above)
# for payer in sortbypayer:
#   print("Payer: %s --- %s members" % (payer[0],payer[1]))


###################################################
### SECTION 2:                                  ###
### ANALYSIS BASED ON model_scores_by_zip TABLE ###

print("""
**************************************
*** ANALYSIS BASED ON MODEL SCORES ***""")

# # *** sqlite viewer having trouble previewing this table; created function to print a Pandas dataframe to preview view relevant data: *** #
# def print_pandas_table(table_name, cols="*"):
#   dataframe = pd.read_sql_query("SELECT %s FROM %s" % (cols, table_name), connection)
#   print(dataframe)
# print_pandas_table('model_scores_by_zip','zcta,algorex_sdoh_composite_score,food_access_score,social_isolation_score')


# Store distinct members + zip codes for analysis of model_scores_by_zip:
distinct_members_by_zip = cur.execute("SELECT DISTINCT member_id,zip_code FROM std_member_info").fetchall()


# --------------------------------------
### FOOD ACCESS SCORE LESS THAN [TARGET]:
target_score = 2.0
foodaccess_lessthan = firstIndexCur.execute("SELECT zcta,food_access_score FROM model_scores_by_zip WHERE food_access_score < %s" % target_score).fetchall()

count = 0
for member in distinct_members_by_zip:
  if member[1] in foodaccess_lessthan:
    count += 1

print("\nMembers with 'Food Access Score' less than %s:" % target_score)
print("--- There are %s members residing across %s zip codes with a 'Food Access Score' less than %s." % (count,len(foodaccess_lessthan),target_score))

# -----------------------------------------
### AVG SOCIAL ISOLATION SCORE FOR MEMBERS:
print("\nAverage 'Social Isolation' score for all distinct members")

zip_scores_dict = {}
social_iso_zip_scores = cur.execute("SELECT zcta,social_isolation_score FROM model_scores_by_zip ORDER BY zcta").fetchall()
for pair in social_iso_zip_scores:
  zip_scores_dict[pair[0]] = float(pair[1])

social_iso_sum = 0

for member in distinct_members_by_zip:
  # FIRST ATTEMPT: very inefficient for processing speed
  # score = firstIndexCur.execute("SELECT social_isolation_score FROM model_scores_by_zip WHERE zcta=%s" % member[1]).fetchone()

  score = zip_scores_dict[member[1]]
  social_iso_sum += score

avg_social_iso_members = social_iso_sum / len(distinct_members_by_zip)

print("--- The average social isolation score for all distinct members is %s." % round(avg_social_iso_members,4))

# ----------------------------------------------------------
### WHICH MEMBERS LIVE IN ZIP WITH HIGHEST ALGOREX_..._SCORE
print("\nAlgorex SDOH Composite Score:")

max_algorex_zip = firstIndexCur.execute("SELECT zcta,algorex_sdoh_composite_score FROM model_scores_by_zip WHERE algorex_sdoh_composite_score = (SELECT MAX(algorex_sdoh_composite_score) FROM model_scores_by_zip)").fetchone()
# max_algorex_members = cur.execute("SELECT DISTINCT member_id,member_first_name,member_last_name FROM std_member_info WHERE zip_code='%s'" % max_algorex_zip).fetchall()
dataframe = pd.read_sql_query("SELECT DISTINCT member_id,zip_code FROM std_member_info WHERE zip_code='%s'" % max_algorex_zip, connection)

print("--- %s members live in the zip code with the highest Algorex SDOH Composite score:" % len(dataframe))
print(dataframe)




connection.close()