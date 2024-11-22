import streamlit.components.v1 as components
import json

import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def render_mindmap(mindmap_data: dict) -> None:
    """Render the mindmap using a custom HTML/JS component with error handling"""
    try:
        logger.info("マインドマップの描画を開始します")
        
        # JSONデータをエスケープ
        safe_json = json.dumps(mindmap_data).replace('"', '&quot;')
        
        html_template = """
    <div id="mindmap-container" style="width: 100%; height: 700px; background: rgba(255, 255, 255, 0.1); border-radius: 10px;">
        <style>
            /* Base node styles */
            .node {
                margin: 10px 15px;
                padding: 8px;
                cursor: pointer;
                transition: all 0.3s ease;
                transform-origin: center;
            }
            
            /* Node background styles */
            .node rect {
                fill: rgba(255, 255, 255, 0.95);
                rx: 8px;
                ry: 8px;
                stroke: rgba(0, 0, 0, 0.12);
                stroke-width: 1.5px;
                filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.15));
            }
            
            /* Node content styles */
            .node-content {
                padding: 10px;
                display: flex;
                align-items: center;
                justify-content: flex-start;
            }
            
            /* Node text styles */
            .node text {
                font-family: "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif;
                font-size: 14px;
                fill: #333333;
                dominant-baseline: middle;
                font-weight: 500;
                letter-spacing: 0.3px;
            }
            .node:hover {
                transform: scale(1.02);
                box-shadow: 0 6px 8px rgba(0, 0, 0, 0.15);
            }
            /* Node type specific styles */
            .node.root rect {
                fill: url(#rootGradient);
            }
            .node.root text {
                fill: white;
                font-weight: bold;
            }
            
            /* Category nodes */
            .node.critical-category rect { fill: rgba(255, 200, 200, 0.9); }
            .node.main-category rect { fill: rgba(200, 255, 200, 0.9); }
            .node.sub-category rect { fill: rgba(200, 200, 255, 0.9); }
            
            /* Content nodes */
            .node.critical rect { fill: rgba(255, 180, 180, 0.9); }
            .node.important rect { fill: rgba(255, 220, 180, 0.9); }
            .node.normal rect { fill: rgba(220, 255, 220, 0.9); }
            .node.auxiliary rect { fill: rgba(220, 220, 255, 0.9); }
            
            /* Continuation nodes */
            .node.continuation rect { 
                fill: rgba(245, 245, 245, 0.9);
            }
            .node.continuation text {
                font-style: italic;
            }
            .connection {
                stroke: rgba(150, 150, 150, 0.6);
                stroke-width: 2px;
                transition: stroke-width 0.3s ease;
            }
            .connection:hover {
                stroke-width: 3px;
                stroke: rgba(100, 100, 100, 0.8);
            }
            .node text {
                font-family: "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif;
            }
        </style>
        <script src="https://d3js.org/d3.v7.min.js"></script>
        <script>
            const mindmapData = JSON.parse(`{}`);
            
            const width = document.getElementById('mindmap-container').offsetWidth;
            const height = 700;
            
            const tree = d3.tree()
                .size([height - 100, width - 200])
                .separation((a, b) => (a.parent == b.parent ? 1 : 1.2));
            
            const root = d3.hierarchy(mindmapData);
            
            const svg = d3.select('#mindmap-container')
                .append('svg')
                .attr('width', width)
                .attr('height', height);
                
            // Define gradient for root node
            const defs = svg.append('defs');
            const gradient = defs.append('linearGradient')
                .attr('id', 'rootGradient')
                .attr('x1', '0%')
                .attr('y1', '0%')
                .attr('x2', '100%')
                .attr('y2', '100%');
                
            gradient.append('stop')
                .attr('offset', '0%')
                .attr('stop-color', 'rgba(100, 180, 255, 0.9)');
                
            gradient.append('stop')
                .attr('offset', '100%')
                .attr('stop-color', 'rgba(70, 150, 255, 0.9)');
                
            // Main container group
            const container = svg.append('g')
                .attr('transform', 'translate(100, 50)');
                
            const nodes = tree(root);
            
            // Add connections with curved paths and improved positioning
            svg.selectAll('.connection')
                .data(nodes.links())
                .join('path')
                .attr('class', 'connection')
                .attr('d', d3.linkHorizontal()
                    .x(d => d.y)
                    .y(d => d.x))
                .attr('transform', 'translate(0, 0)');
                
            // Add node groups
            const node = svg.selectAll('.node')
                .data(nodes.descendants())
                .join('g')
                .attr('class', d => `node ${d.data.class || ''}`)
                .attr('transform', d => `translate(${d.y},${d.x})`);
                
            // Add node backgrounds
            node.append('rect')
                .attr('rx', 8)
                .attr('ry', 8);
                
            console.log('Adding text content to nodes');
            // Add text content with improved positioning
            const textContainer = node.append('g')
                .attr('class', 'node-content');

            textContainer.append('text')
                .text(d => d.data.text)
                .attr('dy', '0.32em')
                .attr('x', 10)
                .each(function(d) {
                    console.log('Processing text for node:', d.data.text);
                    // Wrap text if too long
                    const text = d3.select(this);
                    const words = d.data.text.split(/\\s+/);
                    const lineHeight = 1.1;
                    const y = text.attr('y');
                    const dy = parseFloat(text.attr('dy'));
                    let tspan = text.text(null).append('tspan')
                        .attr('x', 5)
                        .attr('y', y)
                        .attr('dy', dy + 'em');
                    
                    let line = [];
                    let lineNumber = 0;
                    
                    words.forEach(word => {
                        line.push(word);
                        tspan.text(line.join(' '));
                        
                        if (tspan.node().getComputedTextLength() > 150) {
                            line.pop();
                            tspan.text(line.join(' '));
                            line = [word];
                            tspan = text.append('tspan')
                                .attr('x', 5)
                                .attr('y', y)
                                .attr('dy', ++lineNumber * lineHeight + dy + 'em')
                                .text(word);
                        }
                    });
                });
                
            console.log('Adjusting node sizes');
            // Adjust rectangle sizes to fit text with improved calculations
            node.selectAll('rect')
                .attr('width', function(d) {
                    try {
                        const textNode = this.parentNode.querySelector('text');
                        const textBox = textNode.getBBox();
                        const padding = 40;
                        const minWidth = 100;
                        const width = Math.max(textBox.width + padding, minWidth);
                        return width;
                    } catch (error) {
                        console.error('Error calculating width:', error);
                        return 150; // fallback width
                    }
                })
                .attr('height', function(d) {
                    try {
                        const textBox = this.parentNode.querySelector('text').getBBox();
                        const height = Math.max(textBox.height + 20, 40); // minimum height of 40px
                        console.log('Node height calculated:', height);
                        return height;
                    } catch (error) {
                        console.error('Error calculating height:', error);
                        return 50; // fallback height
                    }
                })
                .attr('x', -10)
                .attr('y', function(d) {
                    try {
                        const textBox = this.parentNode.querySelector('text').getBBox();
                        return -textBox.height/2 - 10;
                    } catch (error) {
                        console.error('Error calculating y position:', error);
                        return -25; // fallback y position
                    }
                });
                
            // Add click handlers for node folding
            node.on('click', function(event, d) {
                if (d.children) {
                    d._children = d.children;
                    d.children = null;
                } else {
                    d.children = d._children;
                    d._children = null;
                }
                update(d);
            });
            
            function update(source) {
                const duration = 750;
                
                try {
                    // Compute the new tree layout with optimized spacing
                    const nodes = tree.nodeSize([50, 120])(root);
                    const descendants = nodes.descendants();
                    const links = nodes.links();
                    
                    // Calculate bounds and center the layout
                    let left = Infinity;
                    let right = -Infinity;
                    let top = Infinity;
                    let bottom = -Infinity;
                    
                    descendants.forEach(d => {
                        if (d.x < left) left = d.x;
                        if (d.x > right) right = d.x;
                        if (d.y < top) top = d.y;
                        if (d.y > bottom) bottom = d.y;
                    });
                    
                    const width = right - left;
                    const height = bottom - top;
                    
                    // Update the nodes with error handling
                    const node = svg.selectAll('g.node')
                        .data(descendants, d => d.id || (d.id = ++i));
                    
                    // Enter any new nodes at the parent's previous position
                    const nodeEnter = node.enter().append('g')
                        .attr('class', d => `node ${d.data.class || ''}`)
                        .attr('transform', d => {
                            const x = source.x0 || source.x;
                            const y = source.y0 || source.y;
                            return `translate(${y},${x})`;
                        });
                    
                    // Update connections with smooth transitions and error handling
                    const link = svg.selectAll('.connection')
                        .data(links, d => d.target.id || Math.random());
                
                // Enter any new links at the parent's previous position
                link.enter().insert('path', 'g')
                    .attr('class', 'connection')
                    .attr('d', d3.linkHorizontal()
                        .x(d => d.y)
                        .y(d => d.x));
                
                // Transition links to their new position
                link.transition()
                    .duration(duration)
                    .attr('d', d3.linkHorizontal()
                        .x(d => d.y)
                        .y(d => d.x));
                
                // Transition nodes to their new position
                const nodeUpdate = node.merge(nodeEnter)
                    .transition()
                    .duration(duration)
                    .attr('transform', d => `translate(${d.y},${d.x})`);
                
                // Store the old positions for transitions
                descendants.forEach(d => {
                    d.x0 = d.x;
                    d.y0 = d.y;
                });
            }
        </script>
    </div>
    """
    
    # HTMLコンテンツを作成
        html_content = html_template.format(safe_json)
        
        # コンポーネントをレンダリング
        components.html(
            html_content,
            height=750,
            scrolling=True
        )
        logger.info("マインドマップの描画が完了しました")
        
    except Exception as e:
        logger.error(f"マインドマップの描画中にエラーが発生しました: {str(e)}")
        raise
