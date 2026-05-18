import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
import math

def subcluster_vocabulary(input_excel, output_excel, target_words_per_subunit=90):
    print("1. 正在读取聚类后的单词表...")
    sheets = pd.read_excel(input_excel, sheet_name=None)
    print(f"成功读取 {len(sheets)} 个大单元")

    # 初始化模型
    print("2. 正在加载语义向量模型...")
    model = SentenceTransformer('all-MiniLM-L6-v2')

    all_subclusters = {}

    for unit_name, df in sheets.items():
        print(f"\n处理 {unit_name} ({len(df)} 个单词)...")

        # 获取单词列表（假设第一列是单词）
        words = df.iloc[:, 0].dropna().astype(str).tolist()

        # 计算聚类数：目标每个子单元约90词
        num_subclusters = math.ceil(len(words) / target_words_per_subunit)
        print(f"  将分为 {num_subclusters} 个子主题单元，每个约 {target_words_per_subunit} 词")

        # 向量化所有单词
        print("    正在向量化...")
        embeddings = model.encode(words, show_progress_bar=False)

        # 聚类
        kmeans = KMeans(n_clusters=num_subclusters, random_state=42, n_init="auto")
        cluster_labels = kmeans.fit_predict(embeddings)

        # 将聚类结果添加到DataFrame
        df_copy = df.copy()
        df_copy['sub_cluster'] = cluster_labels

        # 按子聚类分组
        for sub_cluster_id in range(num_subclusters):
            cluster_words = df_copy[df_copy['sub_cluster'] == sub_cluster_id].drop('sub_cluster', axis=1)
            sub_sheet_name = f"{unit_name}_Sub{sub_cluster_id+1}"
            all_subclusters[sub_sheet_name] = cluster_words
            print(f"    {sub_sheet_name}: {len(cluster_words)} 个单词")

    print(f"\n4. 正在导出到 {output_excel}...")
    with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
        for sheet_name, sub_df in all_subclusters.items():
            sub_df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"  写入 {sheet_name}: {len(sub_df)} 个单词")

    print(f"🎉 细分聚类完成！文件保存为: {output_excel}")

# 运行程序
if __name__ == "__main__":
    subcluster_vocabulary(
        input_excel='clustered_words.xlsx',
        output_excel='subclustered_words.xlsx',
        target_words_per_subunit=90  # 每个子单元约90词
    )