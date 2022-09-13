import sqlite3
import pandas as pd

connection = sqlite3.connect("interview.db")
cur = connection.cursor()
firstIndexCur = connection.cursor()
firstIndexCur.row_factory = lambda cursor, row: row[0]


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

######################################################
### CREATE FUNCTION TO:                            ###
### IMPORT DATA TO NEW TABLE BY ELIGIBILITY MONTH, ###
### UPDATE NON-STANDARD DATE FORMATTING            ###

def import_data():
  allrosters = []

  allrosters = firstIndexCur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%roster%' ORDER BY name").fetchall()

  for roster in allrosters:

    reqdCols = ("Person_Id,"
                "First_Name,"
                "Last_Name,"
                "Dob,"
                "Street_Address,"
                "City,"
                "State,"
                "Zip,"
                "payer")
    
    thiscur = connection.cursor()
    
    ######################################################################
    ### UPDATE DATE FORMATTING IF 'mm/dd/YYYY' INSTEAD OF 'YYYY-mm-DD' ###

    test = firstIndexCur.execute("SELECT eligibility_start_date FROM " + roster).fetchone()

    if "/" in test:
      print("ERROR: WRONG DATE FORMAT", roster, test )

      # # OLD IDEA #
      # print(thiscur.execute("SELECT eligibility_start_date,STRFTIME('%Y-%m-%d', eligibility_start_date) AS formatted FROM " + roster).fetchone())
      # continue

      data = thiscur.execute("SELECT eligibility_start_date,eligibility_end_date,Person_Id FROM %s" % (roster)).fetchall()
      
      for t in data:
        start_split, end_split = t[0].split("/"), t[1].split("/")
        newstart = "%s-%s-%s" % (start_split[2], start_split[0], start_split[1])
        newend = "%s-%s-%s" % (end_split[2], end_split[0], end_split[1])
        # newstart = start_split[2] + "-" + start_split[0] + "-" + start_split[1]
        # newend = end_split[2] + "-" + end_split[0] + "-" + end_split[1]

        sql = ("UPDATE %s SET eligibility_start_date = '%s', eligibility_end_date = '%s' WHERE Person_Id = '%s'" % (roster, newstart, newend, t[2]))
        
        thiscur.execute(sql)
        connection.commit()
      #### END UPDATE DATE FORMAT #####


    # SELECT all required columns from each ROSTER where eligibility must include 2022-04-01
    data = thiscur.execute( "SELECT %s FROM %s WHERE eligibility_start_date<='2022-04-01' AND eligibility_end_date>'2022-04-01'" % (reqdCols, roster)).fetchall()

    # INSERT all records into STD_MEMBER_INFO table
    thiscur.executemany("INSERT INTO std_member_info VALUES(?,?,?,?,?,?,?,?,?)", data)
    connection.commit()

### RUN THE FUNCTION
# import_data()


###################################################################
### CHECK FOR DISTINCT MEMBERS, HOW MANY MEMBERS ARE DUPLICATES ###
memberscount = firstIndexCur.execute("SELECT count(*) FROM std_member_info").fetchone()
members_distinct = cur.execute("SELECT DISTINCT member_id FROM std_member_info").fetchall()
duplicateentries = memberscount - len(members_distinct)

print("""
*****************************
*** IMPORTED DATA SUMMARY *** """)

print("There are %s entries for members eligible in April, 2022. This includes:" % memberscount) 
print("--- %s distinct members." % len(members_distinct))
print("--- %s duplicate entries." % (duplicateentries))


#######################
### SORT BY "PAYER" ###
payersql = "SELECT payer,COUNT(DISTINCT member_id) AS members FROM std_member_info GROUP BY payer"
sortbypayer = cur.execute(payersql).fetchall()
payer_dataframe = pd.read_sql_query(payersql, connection)
payer_dataframe['pct (%)'] = round(payer_dataframe.members / len(members_distinct) * 100,2)

print("""
**************************
*** BREAKDOWN BY PAYER ***""")
# for payer in sortbypayer:
#   print("Payer: %s --- %s members" % (payer[0],payer[1]))
print(payer_dataframe)




#############################################
### ANALYSIS BASED ON model_scores_by_zip ###
print("""
**************************************
*** ANALYSIS BASED ON MODEL SCORES ***""")

# # *** sqlite viewer having trouble previewing this table; created function to print a Pandas dataframe to preview view relevant data: *** #
def print_pandas_table(table_name, cols="*"):
  dataframe = pd.read_sql_query("SELECT %s FROM %s" % (cols, table_name), connection)
  print(dataframe)

# print_pandas_table('model_scores_by_zip','zcta,algorex_sdoh_composite_score,food_access_score,social_isolation_score')




# Get distinct members + zip codes for analysis of model_scores_by_zip #
members_distinct_zip = cur.execute("SELECT DISTINCT member_id,zip_code FROM std_member_info").fetchall()

# -------------------------------
### FOOD ACCESS SCORE LESS THAN [TARGET]
target_score = 2.0
print("\nMembers with 'Food Access Score' less than %s:" % target_score)
foodaccess_lessthan = firstIndexCur.execute("SELECT zcta,food_access_score FROM model_scores_by_zip WHERE food_access_score < %s" % target_score).fetchall()

count = 0
for member in members_distinct_zip:
  if member[1] in foodaccess_lessthan:
    count += 1

print("--- There are %s members residing across %s zip codes with a 'Food Access Score' less than %s." % (count,len(foodaccess_lessthan),target_score))


### AVG SOCIAL ISOLATION SCORE FOR MEMBERS ###
print("\nAverage 'Social Isolation' score for all distinct members")

zip_scores_dict = {}
social_iso_zip_scores = cur.execute("SELECT zcta,social_isolation_score FROM model_scores_by_zip ORDER BY zcta").fetchall()
for pair in social_iso_zip_scores:
  zip_scores_dict['%s' % pair[0]] = float(pair[1])

social_iso_sum = 0

for member in members_distinct_zip:
  # score = firstIndexCur.execute("SELECT social_isolation_score FROM model_scores_by_zip WHERE zcta=%s" % member[1]).fetchone()

  score = zip_scores_dict['%s' % member[1]]
  social_iso_sum += score

avg_social_iso_members = social_iso_sum / len(members_distinct_zip)

print("--- The average social isolation score for all distinct members is %s." % round(avg_social_iso_members,4))


### WHICH MEMBERS LIVE IN ZIP WITH HIGHEST ALGOREX_..._SCORE ###
print("\nAlgorex SDOH Composite Score:")

max_algorex_zip = firstIndexCur.execute("SELECT zcta,algorex_sdoh_composite_score FROM model_scores_by_zip WHERE algorex_sdoh_composite_score = (SELECT MAX(algorex_sdoh_composite_score) FROM model_scores_by_zip)").fetchone()
max_algorex_members = cur.execute("SELECT DISTINCT member_id,member_first_name,member_last_name FROM std_member_info WHERE zip_code='%s'" % max_algorex_zip).fetchall()
dataframe = pd.read_sql_query("SELECT DISTINCT member_id,zip_code FROM std_member_info WHERE zip_code='%s'" % max_algorex_zip, connection)

print("--- %s members live in the zip code with the highest Algorex SDOH Composite score:" % len(max_algorex_members))
# print(dataframe)




connection.close()



"""
DRAFT EMAIL TO PROJECT MANAGER (Non-techincal):
- Steps you took, probs with data, requested outputs

Good morning [project manager],

I was able to combine the data you sent fom all 5 rosters of members whose elibigility was active as of April, 2022, and provide the analysis that you requested. 

For the most part, this was a relatively straightforward process: For each roster, I limited my search to those members whose eligibility start/end dates were on either side of '2022-04-01', which guarantees they were eligible in April, 2022. Because there were some duplicate entries across the 5 rosters, I later sorted the data even further to include only *distinct* member id entries, so all of the analysis should reflect a true roster of unique members, (i.e. without duplicates, which would have potentially skewed counts and averages). I've included the difference in total entries versus unique entries below to give you some idea of what I mean.

I did find one small hiccup with the data: While the database expects dates to be stored in the format "YYYY-MM-DD", all of the dates in the "roster_2" table were stored in the format "MM/DD/YYYY". This required a small workaround in which I reformatted the data in the original "roster_2" file to the correct date format *before* I pulled out members from April, 2022. I assumed this was okay, since the original file was emailed to me and could therefore be recovered if needed, but in the future we should try to ensure that dates are formatted correctly on the user's end before being stored in our rosters.

Below, please find the data analysis requested. Please note that in the interest of member confidentiality, I recorded each member by id number only; if you require further identifying information, that can be included.  If you have any further questions, please don't hesitate to reach out!

*****************************
*** IMPORTED DATA SUMMARY ***
There are 122834 entries for members eligible in April, 2022. This includes:
--- 90420 distinct members.
--- 32414 duplicate entries.

**************************
*** BREAKDOWN BY PAYER ***
  payer  members  pct (%)
0  Madv    33930    37.52
1  Mdcd    56490    62.48

**************************************
*** ANALYSIS BASED ON MODEL SCORES ***

Members with 'Food Access Score' less than 2.0:
--- There are 6958 members residing across 136 zip codes with a 'Food Access Score' less than 2.0.

Average 'Social Isolation' score for all distinct members
--- The average social isolation score for all distinct members is 3.0699.

Algorex SDOH Composite Score:
--- 40 members live in the zip code with the highest algorex_sdog_composite_score:
    member_id
0    15404143
1    15537550
2    15363143
3    15375855
4    15359217
5    15447186
6    15487938
7    15493624
8    15506131
9    15387928
10   15389759
11   15403845
12   15459547
13   15495072
14   15499581
15   15525968
16   15355184
17   15370952
18   15377751
19   15468254
20   15469273
21   15516212
22   15531858
23   15534578
24   15476293
25   15348534
26   15377622
27   15383576
28   15456488
29   15460500
30   15484118
31   15502702
32   15456560
33   15340102
34   15346807
35   15389381
36   15482255
37   15484216
38   15486908
39   15489640
"""