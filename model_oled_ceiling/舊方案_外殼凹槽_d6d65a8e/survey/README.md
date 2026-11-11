# 1F 天花板量測與位置搜尋

依序執行（Blender 5.2；`<S>` 是英文路徑的工作資料夾，先把 fire_model.blend 複製進去）：

1. `blender -b <S>/fm.blend --python 1_scan.py -- <S>/occ.npz`：0.5 mm 網格垂直射線，記錄 1F 每個零件的實體區間
2. `blender -b --python 2a_derive.py -- <S>`、`blender -b --python 2b_derive.py -- <S>`：天花板底面、連續實體頂、排線溝、上方空間、下方牆的遮罩（另輸出 map_*.png）
3. `blender -b --python 2c_components.py -- <S>`：列出孔、塞子、溝槽、銷孔的位置與尺寸
4. `blender -b --python 2d_map.py -- <S>`：可用區域圖
5. `blender -b --python 3_search.py -- <S> <允許切溝 0/1> <不要求排針上方空間 0/1>`：每個路口 × 0.96／0.91 × 4 方向窮舉 → `search_XY.json`

`位置搜尋結果.txt` 是四種條件的結果；採用的是「切溝＋焊線」（`3_search.py -- <S> 1 1`）。

6. `4a/4b/4c_*.py`：把其他 OLED 凹槽當禁區，重新搜尋中心與 SW（凹槽間壁厚 1.5／1.2～0／允許吃掉 5×5 路口孔）。
