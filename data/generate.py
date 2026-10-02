"""Deterministic, synthetic fixtures. No recalled production/exam data is included."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

HERE = Path(__file__).resolve().parent
TEXT = {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}}
def text():
    return json.loads(json.dumps(TEXT))
def entry(name, properties, documents, *, cluster="cluster1", shards=1, replicas=0):
    return {"cluster": cluster, "index": name,
            "settings": {"number_of_shards": shards, "number_of_replicas": replicas},
            "mappings": {"properties": properties},
            "documents": [{"_id": f"{name}-{i:04d}", "_source": d} for i, d in enumerate(documents, 1)]}

def generate():
    out=[]
    food=[]
    for i in range(96):
        names=["Classic potato chips", "Potato baked chips", "Sea salt crackers", "Fresh potatoes", "Potato chips family pack", "Corn tortilla chips"]
        food.append({"name": names[i%6], "brand": "Potato Chips House" if i%7==0 else f"Pantry {i%5}",
            "manufacturer": "potato chips cooperative" if i%11==0 else "Harvest Foods",
            "ingredients": ["potatoes for crispy chips with sea salt", "corn flour and salt", "sunflower oil for baking", "potato flakes and pepper"][i%4],
            "weight": 100+(i%8)*25, "sku": f"SKU-{i:04d}", "calories": 180+i%180,
            "organic": i%3==0})
    out.append(entry("food-ingredients",{"name":text(),"brand":text(),"manufacturer":text(),"ingredients":text(),"weight":{"type":"long"},"sku":{"type":"keyword"},"calories":{"type":"integer"},"organic":{"type":"boolean"}},food))
    inspections=[]
    for i in range(96):
        bits=i%8
        inspections.append({"category": "fire fire safety" if bits&1 else "building safety", "item": ("repair fire alarm" if bits&2 else "repair exit door") if i%4!=3 else ("fire alarm" if bits&2 else "exit door"),
            "item_description": "fire equipment inspection" if bits&4 else "annual equipment inspection",
            "street_number": 100+i, "street_name":["죽전로","한강로","Maple Street","Oak Road"][i%4],
            "neighborhood":["아무개","상암","Central","North"][i%4],"zipcode":f"{16800+i:05d}",
            "date_filed":f"2022-08-{1+(i//3)%28:02d}T09:00:00Z", "passed":i%5!=0})
    out.append(entry("inspections",{"category":text(),"item":text(),"item_description":text(),"street_number":{"type":"integer"},"street_name":text(),"neighborhood":{"type":"keyword"},"zipcode":{"type":"keyword"},"date_filed":{"type":"date"},"passed":{"type":"boolean"}},inspections))
    flights=[]
    for i in range(240):
        k=i%6; airline=["AS","UA","DL","AA","WN","JB"][k]
        flights.append({"Airline":airline,"ActualElapsedTime":float([360,310,240,190,140,90][k]+(i%13)),
            "DistanceInMiles":float(500+k*180+i%37),"FlightDate":(datetime(2022,1,1,tzinfo=timezone.utc)+timedelta(hours=i*7)).isoformat().replace('+00:00','Z'),"FlightNumber":f"{airline}{100+i}"})
    out.append(entry("flights",{"Airline":{"type":"keyword"},"ActualElapsedTime":{"type":"double"},"DistanceInMiles":{"type":"double"},"FlightDate":{"type":"date"},"FlightNumber":{"type":"keyword"}},flights))
    movies=[]
    profits=[-5000000,-1,0,250000,999999,1000000,1500000,9999999,10000000,25000000]
    for i in range(120):
        title=["Star Voyage", "A Star Returns", "The Star and Me", "To My City", "Travel to the Moon", "You and Me", "My Summer Story", "River Stories"][i%8]
        # At least 45 star hits and repeated revenues exercise pagination/tie breaking.
        budget=10000000+(i//10)*1000000
        movies.append({"movie_id":1000+i,"title":title,"budget":budget,"revenue":budget+profits[i%10],
            "tags":"romantic comedy" if i%3==0 else ["science fiction","documentary","family drama"][i%3],
            "release_date":f"2020-{1+i%12:02d}-{1+i%27:02d}","rating":round(5+(i%40)/10,1)})
    out.append(entry("movie_data",{"movie_id":{"type":"long"},"title":text(),"budget":{"type":"long"},"revenue":{"type":"long"},"tags":text(),"release_date":{"type":"date"},"rating":{"type":"double"}},movies))
    stocks=[]
    for i in range(80):
        opening=50+i
        stocks.append({"ticker":["AAA","BBB","CCC","DDD"][i%4],"opening-price":float(opening),"closing-price":opening+[-7.0,-5.0,-4.5,-1.0,0.0,4.5,5.0,8.0][i%8],"@timestamp":f"2022-09-{1+i%28:02d}T15:00:00Z"})
    out.append(entry("stock-prices",{"ticker":{"type":"keyword"},"opening-price":{"type":"double"},"closing-price":{"type":"double"},"@timestamp":{"type":"date"}},stocks))
    earthquakes=[]
    for year in (2011,2012,2013):
        for month in range(1,13):
            for k in range(4):
                earthquakes.append({"Date":f"{year}-{month:02d}-{2+k*6:02d}T12:00:00Z","Magnitude":round(2+month/10+k/4,2),"Depth":float(month*3+(3-k)*7),"MagnitudeType":["MWC","MWB","ML","MS"][k],"region":["Pacific","Atlantic","Asia","Europe"][k]})
    out.append(entry("earthquakes",{"Date":{"type":"date"},"Magnitude":{"type":"double"},"Depth":{"type":"double"},"MagnitudeType":{"type":"keyword"},"region":{"type":"keyword"}},earthquakes))
    magnitude=[{"MagnitudeType":k,"MagnitudeTypeDesc":v} for k,v in [("MWC","Centroid moment magnitude"),("MWB","Body-wave moment magnitude"),("ML","Local magnitude"),("MS","Surface-wave magnitude")]]
    out.append(entry("magnitude_type",{"MagnitudeType":{"type":"keyword"},"MagnitudeTypeDesc":{"type":"keyword"}},magnitude))
    for cluster,index in [("cluster1","listings"),("cluster2","listings2")]:
        docs=[]
        for i in range(64):
            docs.append({"listing_id":f"{cluster}-{i:03d}","summary":["Quiet apartment near the city center", "A view of the city and a shopping center", "Walk to the city center and museums", "Country house outside town"][i%4],"review_scores_rating":90+i%11,"city":["Seoul","Berlin","Tokyo","Paris"][i%4],"nightly_price":80+i})
        out.append(entry(index,{"listing_id":{"type":"keyword"},"summary":text(),"review_scores_rating":{"type":"long"},"city":{"type":"keyword"},"nightly_price":{"type":"long"}},docs,cluster=cluster))
    cities=[{"city":n,"population":p,"year":2022} for n,p in [("Seoul",9400000),("Berlin",3600000),("Tokyo",14000000),("Paris",2100000),("Sydney",5300000),("Toronto",2900000),("Madrid",3300000),("Rome",2800000),("Osaka",2700000),("Busan",3300000),("Taipei",2500000),("Lisbon",550000)]]
    for name in ("city_population","city_populations"):
        out.append(entry(name,{"city":{"type":"keyword"},"population":{"type":"long"},"year":{"type":"integer"}},cities,cluster="cluster2"))
    blogs=[]
    for i in range(84):
        authors=([{"uid":"u1","first_name":"david","full_name":"David Kim","job_title":"designer"},{"uid":"u2","first_name":"john","full_name":"John Lee","job_title":"engineer"}]
                 if i%3==0 else [{"uid":"u3","first_name":"david","full_name":"David Park","job_title":"software engineer"}] if i%3==1 else [{"uid":"u4","first_name":"alice","full_name":"Alice Han","job_title":"platform engineer"}])
        d={"title":["Open Source Search", "Elastic Platform Guide", "Reliable Search Systems", "Search Stories"][i%4],
            "content":["Open source software enables elastic search. Learn certified engineer skills.","Search with elastic and build dependable systems.","An open source guide to indexing and search.","Building resilient applications and distributed data systems."][i%4],
            "summary":["An open source search tutorial","Practical elastic engineering","Open platforms for search"][i%3],
            "publish_date":f"2024-{1+i%12:02d}-{1+i%27:02d}T12:00:00Z", "authors":authors,"popularity":50+i,"locale":"en-us"}
        if i%7: d['category']=f"c{i%4}"
        blogs.append(d)
    out.append(entry("blogs",{"title":text(),"content":text(),"summary":text(),"publish_date":{"type":"date"},"authors":{"properties":{"uid":{"type":"keyword"},"first_name":text(),"full_name":text(),"job_title":text()}},"category":{"type":"keyword"},"popularity":{"type":"long"},"locale":{"type":"keyword"}},blogs))
    out.append(entry("categories",{"uid":{"type":"keyword"},"title":{"type":"keyword"}},[{"uid":f"c{i}","title":v} for i,v in enumerate(["Culture","Engineering","News","Search"])]))
    out.append(entry("legacy-drinks",{"name":text(),"price":{"type":"long"}},[{"name":"yoo-hoo","price":2},{"name":"yoohoo","price":3},{"name":"water","price":1}]))
    for name,replicas in [("legacy-index1",1),("legacy-index2",0)]:
        out.append(entry(name,{"message":{"type":"text"},"record_id":{"type":"keyword"}},[{"message":f"Allocation fixture {i}","record_id":str(i)} for i in range(12)],replicas=replicas))
    return out

if __name__=='__main__':
    data=generate()
    (HERE/'fixtures.json').write_text(json.dumps({"synthetic":True,"seed_version":1,"indices":data},ensure_ascii=False,indent=2),encoding='utf-8')
    print('indices',len(data),'documents',sum(len(x['documents']) for x in data))
