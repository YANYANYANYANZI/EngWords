"""Cluster a raw vocabulary workbook into Unit sheets."""

import argparse
from pathlib import Path

import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "data" / "source" / "clustered_words.xlsx"


def cluster_vocabulary(input_excel, output_excel, num_clusters=12):
    print("1. 正在读取单词表...")
    # 读取整个 Excel 文件的所有列
    df = pd.read_excel(input_excel)
    # 去除第一列为空值的行
    df = df.dropna(subset=[df.columns[0]])
    # 第一列作为单词列表
    words = df[df.columns[0]].astype(str).tolist()
    print(f"成功读取 {len(words)} 个单词！")

    print("2. 正在将单词转化为语义向量 (这可能需要几十秒，初次运行会自动下载模型)...")
    # 加载一个轻量级的、专门用于生成句子/单词向量的模型
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = model.encode(words, show_progress_bar=True)

    print(f"3. 正在使用 K-Means 算法将单词聚类为 {num_clusters} 组...")
    # 初始化 K-Means 模型
    kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init="auto")
    # 喂入向量进行训练并获取分类标签
    df['cluster'] = kmeans.fit_predict(embeddings)

    print("4. 正在将结果导出到新的 Excel 文件...")
    # 使用 ExcelWriter 将不同的类写入不同的 Sheet
    with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
        for i in range(num_clusters):
            # 筛选出属于当前类别的所有行（保留所有列）
            cluster_words = df[df['cluster'] == i].drop(columns=['cluster'])
            # 写入对应的 Sheet，命名为 Unit_1, Unit_2 ...
            cluster_words.to_excel(writer, sheet_name=f'Unit_{i+1}', index=False)
            print(f"  - Unit_{i+1} 写入了 {len(cluster_words)} 个单词")

    print(f"🎉 大功告成！文件已保存为: {output_excel}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cluster a vocabulary Excel file into Unit sheets.")
    parser.add_argument("input_excel", type=Path, help="Path to the source Excel workbook.")
    parser.add_argument("--output-excel", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--num-clusters", type=int, default=12)
    args = parser.parse_args()
    args.output_excel.parent.mkdir(parents=True, exist_ok=True)
    cluster_vocabulary(args.input_excel, args.output_excel, num_clusters=args.num_clusters)
