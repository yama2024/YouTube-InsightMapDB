import networkx as nx
import plotly.graph_objects as go
import google.generativeai as genai

class MindMapGenerator:
    def __init__(self):
        genai.configure(api_key='YOUR_GEMINI_API_KEY')
        self.model = genai.GenerativeModel('gemini-pro')

    def generate_mindmap(self, text):
        """テキストからマインドマップのデータを生成"""
        prompt = f"""
        以下のテキストから階層的なマインドマップを生成してください。
        以下の形式でJSON形式で出力してください：
        
        {{
            "center": "中心テーマ",
            "branches": [
                {{
                    "name": "メインブランチ1",
                    "sub_branches": ["サブブランチ1", "サブブランチ2"]
                }},
                // 他のブランチ...
            ]
        }}
        
        テキスト:
        {text}
        """
        
        try:
            response = self.model.generate_content(prompt)
            return eval(response.text)  # JSON文字列を辞書に変換
        except Exception as e:
            raise Exception("マインドマップの生成に失敗しました")

    def create_visualization(self, mindmap_data):
        """マインドマップの可視化を生成"""
        G = nx.Graph()
        
        # ノードとエッジの追加
        center = mindmap_data['center']
        G.add_node(center)
        
        # 色の設定
        node_colors = ['#1B365D']  # 中心ノードの色
        edge_colors = []
        
        # 各ブランチの追加
        for i, branch in enumerate(mindmap_data['branches']):
            G.add_node(branch['name'])
            G.add_edge(center, branch['name'])
            node_colors.append('#4A90E2')
            edge_colors.append('#8AB4F8')
            
            # サブブランチの追加
            for sub in branch['sub_branches']:
                G.add_node(sub)
                G.add_edge(branch['name'], sub)
                node_colors.append('#7FB3D5')
                edge_colors.append('#8AB4F8')
        
        # レイアウトの計算
        pos = nx.spring_layout(G)
        
        # プロットの作成
        edge_trace = []
        for edge in G.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_trace.append(
                go.Scatter(
                    x=[x0, x1], y=[y0, y1],
                    line=dict(width=2, color='#8AB4F8'),
                    hoverinfo='none',
                    mode='lines'
                )
            )

        node_trace = go.Scatter(
            x=[pos[node][0] for node in G.nodes()],
            y=[pos[node][1] for node in G.nodes()],
            mode='markers+text',
            marker=dict(
                size=30,
                color=node_colors,
                line_width=2
            ),
            text=list(G.nodes()),
            textposition="middle center",
            hoverinfo='text'
        )

        # レイアウトの設定
        layout = go.Layout(
            showlegend=False,
            hovermode='closest',
            margin=dict(b=20,l=5,r=5,t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )

        # 図の作成
        fig = go.Figure(data=edge_trace + [node_trace], layout=layout)
        return fig
