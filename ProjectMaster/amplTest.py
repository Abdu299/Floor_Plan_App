from amplpy import AMPL, modules

ampl= AMPL(modules.load())

ampl.eval("""
    param tableT = 5;
    param chair = 2;
    param total_h = 40;

    param table_prof= 500;
    param chair_prof= 300;

    param tableWood = 4;
    param chairWood= 3;
    param totalWood = 48;

    var chairs integer >= 0;
    var tables integer >= 0;

    maximize totalProf:
        table_prof * tables + chair_prof * chairs;
    
    subject to TimeLimit:
        tableT * tables + chair * chairs <= total_h;
    
    subject to WoodLimit:
        tables * tableWood + chairs * chairWood <= totalWood;




"""
)


ampl.option["solver"]= "highs"

ampl.solve()

tables = ampl.get_value("tables")
chairs = ampl.get_value("chairs")
profit = ampl.get_value("totalProf")


print("Tables:", tables)
print("Chairs:", chairs)
print("Profit:", profit)

