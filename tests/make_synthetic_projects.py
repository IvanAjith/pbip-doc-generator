"""Builds three small made-up Power BI projects (inventory, streaming, HR) to prove the generator is not tied to any one business."""
import sys; sys.path.insert(0, '.')
from synthetic_builder import *
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("synthetic_projects")

# ---------------- 1. Inventory (SQL Server, RLS, conditional formatting on one page only, drillthrough page)
def sql_src(t): return f'Source = Sql.Database("sql01.corp.local", "InventoryDB"),\n    Result = Source{{[Schema="dbo",Item="{t}"]}}[Data]'
tables = [
 {"name": "Products", "columns": [("ProductKey","int64"),("SKU","string"),("Category","string"),("UnitCost","double")]},
 {"name": "Warehouses", "columns": [("WarehouseKey","int64"),("Warehouse Name","string"),("Region","string")]},
 {"name": "StockLevels", "columns": [("ProductKey","int64"),("WarehouseKey","int64"),("QtyOnHand","int64"),("QtyOnOrder","int64"),("SnapshotDate","dateTime")]},
 {"name": "Shipments", "columns": [("ProductKey","int64"),("WarehouseKey","int64"),("QtyShipped","int64"),("ShipDate","dateTime"),("COGS","double")]},
]
measures = [
 {"name":"Stock On Hand","expr":"SUM(StockLevels[QtyOnHand])","fmt":"#,0"},
 {"name":"Inventory Value","expr":"SUMX(StockLevels, StockLevels[QtyOnHand] * RELATED(Products[UnitCost]))","fmt":"$#,0"},
 {"name":"COGS Total","expr":"SUM(Shipments[COGS])","fmt":"$#,0"},
 {"name":"Inventory Turnover","expr":"DIVIDE([COGS Total], [Inventory Value])","fmt":"0.0"},
 {"name":"Days of Supply","expr":"DIVIDE([Stock On Hand], DIVIDE(SUM(Shipments[QtyShipped]), 30))","fmt":"0"},
 {"name":"Stockout Rate","expr":'DIVIDE(CALCULATE(DISTINCTCOUNT(StockLevels[ProductKey]), StockLevels[QtyOnHand] = 0), DISTINCTCOUNT(StockLevels[ProductKey]))',"fmt":"0.0%"},
 {"name":"Open Purchase Orders","expr":"SUM(StockLevels[QtyOnOrder])","fmt":"#,0"},
 {"name":"Stock Health","expr":'IF([Days of Supply] < 7, "Low", IF([Days of Supply] > 90, "Overstocked", "Healthy"))'},
]
red_case = [case("_Measures","Stockout Rate",2,"0.05D","#C00000")]  # >= 5% red
pages = [
 {"name":"Overview","nav":["Stock Levels","Replenishment"],"filters":[("Warehouses","Region","wh"),("Products","Category","cat")],
  "cards":[("Stock On Hand",),("Inventory Value",),("Stockout Rate", red_case[0]["Value"]["Literal"] and {"Conditional":{"Cases":[case("_Measures","Stockout Rate",2,"0.05D","#C00000"),case("_Measures","Stockout Rate",3,"0.05D","#2E7D32")]}}),("Inventory Turnover",)]},
 {"name":"Stock Levels","nav":["Overview","Replenishment"],"filters":[("Warehouses","Region","wh"),("Products","Category","cat")],
  "cards":[("Days of Supply",),("Stock Health",)],
  "tables":[{"args":("Products",["SKU","Category"],["Stock On Hand","Days of Supply","Stockout Rate"],10,200),"kw":{"cond":("Stockout Rate",red_case),"title":"Stock by SKU"}}],
  "charts":[{"args":("Warehouses","Warehouse Name","Stock On Hand",450,200),"kw":{"title":"Stock by Warehouse"}}]},
 {"name":"Replenishment","nav":["Overview","Stock Levels"],"filters":[("Warehouses","Region","wh"),("Products","Category","cat")],
  "cards":[("Open Purchase Orders",),("Days of Supply",)],
  "tables":[{"args":("Products",["SKU"],["Open Purchase Orders","Days of Supply"],10,200),"kw":{"title":"Reorder list"}}]},
 {"name":"SKU Detail","drill":True,"hidden":True,"cards":[("Stock On Hand",)]},
]
rls = 'role RegionalManager\n\tmodelPermission: read\n\n\ttablePermission Warehouses = [Region] = USERPRINCIPALNAME()\n'
build(OUT/"inventory", "Inventory Control", sql_src, tables, measures, pages,
      [("StockLevels.ProductKey","Products.ProductKey"),("StockLevels.WarehouseKey","Warehouses.WarehouseKey"),("Shipments.ProductKey","Products.ProductKey")],
      "Overview", rls)

# ---------------- 2. Streaming (Excel, no colour rules at all, no RLS, no sync)
def xl_src(t): return f'Source = Excel.Workbook(File.Contents("C:\\\\data\\\\streaming.xlsx"), null, true),\n    Result = Source{{[Item="{t}",Kind="Sheet"]}}[Data]'
tables = [
 {"name":"Subscribers","columns":[("SubscriberID","string"),("Plan","string"),("Country","string"),("JoinDate","dateTime"),("CancelDate","dateTime")]},
 {"name":"Viewing","columns":[("SubscriberID","string"),("Title","string"),("Genre","string"),("MinutesWatched","double"),("ViewDate","dateTime")]},
 {"name":"Billing","columns":[("SubscriberID","string"),("Amount","double"),("BillDate","dateTime")]},
]
measures = [
 {"name":"Monthly Active Users","expr":"DISTINCTCOUNT(Viewing[SubscriberID])","fmt":"#,0"},
 {"name":"Total Subscribers","expr":"DISTINCTCOUNT(Subscribers[SubscriberID])","fmt":"#,0"},
 {"name":"Churned Subscribers","expr":"CALCULATE(DISTINCTCOUNT(Subscribers[SubscriberID]), NOT ISBLANK(Subscribers[CancelDate]))","fmt":"#,0"},
 {"name":"Churn Rate","expr":"DIVIDE([Churned Subscribers], [Total Subscribers])","fmt":"0.0%"},
 {"name":"Monthly Revenue","expr":"SUM(Billing[Amount])","fmt":"$#,0.00"},
 {"name":"ARPU","expr":"DIVIDE([Monthly Revenue], [Total Subscribers])","fmt":"$#,0.00"},
 {"name":"Watch Hours","expr":"DIVIDE(SUM(Viewing[MinutesWatched]), 60)","fmt":"#,0"},
 {"name":"Hours per Subscriber","expr":"DIVIDE([Watch Hours], [Monthly Active Users])","fmt":"0.0"},
]
nav = ["Home","Content","Audience","Revenue"]
mk = lambda n,extra: {"name":n,"nav":[x for x in nav if x!=n],"filters":[("Subscribers","Country"),("Subscribers","Plan")],**extra}
pages = [
 mk("Home",{"cards":[("Monthly Active Users",),("Churn Rate",),("ARPU",),("Watch Hours",)]}),
 mk("Content",{"cards":[("Watch Hours",),("Hours per Subscriber",)],"charts":[{"args":("Viewing","Genre","Watch Hours",10,200),"kw":{"title":"Watch hours by genre"}}],
               "tables":[{"args":("Viewing",["Title"],["Watch Hours"],450,200),"kw":{"title":"Top titles"}}]}),
 mk("Audience",{"cards":[("Total Subscribers",),("Churned Subscribers",),("Churn Rate",)],"charts":[{"args":("Subscribers","Plan","Total Subscribers",10,200),"kw":{"vt":"donutChart"}}]}),
 mk("Revenue",{"cards":[("Monthly Revenue",),("ARPU",)]}),
]
build(OUT/"streaming","Streaming Analytics",xl_src,tables,measures,pages,
      [("Viewing.SubscriberID","Subscribers.SubscriberID"),("Billing.SubscriberID","Subscribers.SubscriberID")],"Home")

# ---------------- 3. HR (Lakehouse, NO navigation buttons at all, a tooltip page, German-style names with spaces)
def lh_src(t): return f'Source = Lakehouse.Contents(null){{[workspaceId="abc"]}}[Data],\n    Result = Source{{[Id="{t}",ItemKind="Table"]}}[Data]'
tables = [
 {"name":"Employees","columns":[("EmployeeID","string"),("Department","string"),("Hire Date","dateTime"),("Termination Date","dateTime"),("Gender","string")]},
 {"name":"Requisitions","columns":[("ReqID","string"),("Department","string"),("Opened","dateTime"),("Filled","dateTime")]},
]
measures = [
 {"name":"Headcount","expr":"CALCULATE(DISTINCTCOUNT(Employees[EmployeeID]), ISBLANK(Employees[Termination Date]))","fmt":"#,0"},
 {"name":"Leavers","expr":"CALCULATE(DISTINCTCOUNT(Employees[EmployeeID]), NOT ISBLANK(Employees[Termination Date]))","fmt":"#,0"},
 {"name":"Attrition %","expr":"DIVIDE([Leavers], AVERAGEX(VALUES(Employees[Department]), [Headcount]))","fmt":"0.0%"},
 {"name":"Time to Fill (days)","expr":"AVERAGEX(Requisitions, DATEDIFF(Requisitions[Opened], Requisitions[Filled], DAY))","fmt":"0"},
 {"name":"Open Requisitions","expr":"CALCULATE(COUNTROWS(Requisitions), ISBLANK(Requisitions[Filled]))","fmt":"#,0"},
]
pages = [
 {"name":"Workforce","filters":[("Employees","Department")],"cards":[("Headcount",),("Leavers",),("Attrition %",)],
  "charts":[{"args":("Employees","Department","Headcount",10,200),"kw":{"vt":"barChart"}}]},
 {"name":"Hiring","filters":[("Employees","Department")],"cards":[("Time to Fill (days)",),("Open Requisitions",)]},
 {"name":"Tip","tooltip":True,"hidden":True,"cards":[("Headcount",)]},
]
build(OUT/"hr","People Analytics",lh_src,tables,measures,pages,[("Requisitions.Department","Employees.Department")],"Workforce")
# ---------------- 4. Gaming / casino (SQL, percent colour rule, measures that chain on each other, domain terms)
tables = [
 {"name":"Wagers","columns":[("WagerID","string"),("GameID","string"),("PlayerID","string"),("WagerDate","dateTime"),("Amount","double"),("Payout","double")]},
 {"name":"Games","columns":[("GameID","string"),("GameName","string"),("GameType","string"),("HouseEdge","double")]},
]
measures = [
 {"name":"Coin-In","expr":"SUM(Wagers[Amount])","fmt":"$#,0"},
 {"name":"Payouts","expr":"SUM(Wagers[Payout])","fmt":"$#,0"},
 {"name":"Actual Win","expr":"[Coin-In] - [Payouts]","fmt":"$#,0"},
 {"name":"House Edge Avg","expr":"AVERAGE(Games[HouseEdge])","fmt":"0.0%"},
 {"name":"Theoretical Win","expr":"[Coin-In] * [House Edge Avg]","fmt":"$#,0"},
 {"name":"Net Gaming Variance","expr":"[Actual Win] - [Theoretical Win]","fmt":"$#,0"},
 {"name":"Hold %","expr":"DIVIDE([Actual Win], [Coin-In])","fmt":"0.0%"},
 {"name":"Active Players","expr":"DISTINCTCOUNT(Wagers[PlayerID])","fmt":"#,0"},
 {"name":"Win per Active Player","expr":"DIVIDE([Actual Win], [Active Players])","fmt":"$#,0"},
]
pages = [
 {"name":"Floor","nav":["Games"],"filters":[("Games","GameType")],
  "cards":[("Actual Win",),("Theoretical Win",),("Net Gaming Variance",),("Hold %", {"Conditional":{"Cases":[case("_Measures","Hold %",3,"0.03D","#C00000")]}}),("Active Players",)],
  "charts":[{"args":("Games","GameName","Actual Win",10,200),"kw":{"title":"Win by game"}}]},
 {"name":"Games","nav":["Floor"],"filters":[("Games","GameType")],
  "tables":[{"args":("Games",["GameName"],["Coin-In","Payouts","Win per Active Player"],10,200),"kw":{"title":"Game detail"}}]},
]
build(OUT/"gaming","Casino Analytics",sql_src,tables,measures,pages,[("Wagers.GameID","Games.GameID")],"Floor")
print("built synthetic projects in", OUT)
