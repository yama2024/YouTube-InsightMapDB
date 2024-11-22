import streamlit.components.v1 as components
import json

def render_mindmap(mindmap_data: dict) -> None:
    """Render the mindmap using a custom HTML/JS component"""
    
    html_template = """
    <div id="mindmap-container" style="width: 100%; height: 700px; background: rgba(255, 255, 255, 0.1); border-radius: 10px;">
        <style>
            .node {
                padding: 12px;
                border-radius: 8px;
                margin: 5px;
                background: rgba(255, 255, 255, 0.9);
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                transition: all 0.3s ease;
                cursor: pointer;
            }
            .node:hover {
                transform: scale(1.02);
                box-shadow: 0 6px 8px rgba(0, 0, 0, 0.15);
            }
            .node.root {
                background: linear-gradient(135deg, rgba(100, 180, 255, 0.9), rgba(70, 150, 255, 0.9));
                color: white;
                font-weight: bold;
            }
            .node.critical-category { background: rgba(255, 200, 200, 0.9); }
            .node.main-category { background: rgba(200, 255, 200, 0.9); }
            .node.sub-category { background: rgba(200, 200, 255, 0.9); }
            .node.critical { background: rgba(255, 180, 180, 0.9); }
            .node.important { background: rgba(255, 220, 180, 0.9); }
            .node.normal { background: rgba(220, 255, 220, 0.9); }
            .node.auxiliary { background: rgba(220, 220, 255, 0.9); }
            .node.continuation { 
                background: rgba(245, 245, 245, 0.9);
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
            const mindmapData = %s;
            
            const width = document.getElementById('mindmap-container').offsetWidth;
            const height = 700;
            
            const tree = d3.tree()
                .size([height - 100, width - 200])
                .separation((a, b) => (a.parent == b.parent ? 1 : 1.2));
            
            const root = d3.hierarchy(mindmapData);
            
            const svg = d3.select('#mindmap-container')
                .append('svg')
                .attr('width', width)
                .attr('height', height)
                .append('g')
                .attr('transform', 'translate(100, 50)');
                
            const nodes = tree(root);
            
            // Add connections with curved paths
            svg.selectAll('.connection')
                .data(nodes.links())
                .join('path')
                .attr('class', 'connection')
                .attr('d', d3.linkHorizontal()
                    .x(d => d.y)
                    .y(d => d.x));
                
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
                
            // Add text content
            node.append('text')
                .text(d => d.data.text)
                .attr('dy', '0.32em')
                .attr('x', 5)
                .each(function(d) {
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
                
            // Adjust rectangle sizes to fit text
            node.selectAll('rect')
                .attr('width', function(d) {
                    const textBox = this.parentNode.querySelector('text').getBBox();
                    return textBox.width + 20;
                })
                .attr('height', function(d) {
                    const textBox = this.parentNode.querySelector('text').getBBox();
                    return textBox.height + 20;
                })
                .attr('x', -5)
                .attr('y', function(d) {
                    const textBox = this.parentNode.querySelector('text').getBBox();
                    return -textBox.height/2 - 5;
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
                
                const nodes = tree(root);
                
                // Update nodes
                const node = svg.selectAll('g.node')
                    .data(nodes.descendants(), d => d.id || (d.id = ++i));
                    
                // Update connections
                svg.selectAll('.connection')
                    .data(nodes.links())
                    .join('path')
                    .transition()
                    .duration(duration)
                    .attr('d', d3.linkHorizontal()
                        .x(d => d.y)
                        .y(d => d.x));
                        
                node.transition()
                    .duration(duration)
                    .attr('transform', d => `translate(${d.y},${d.x})`);
            }
        </script>
    </div>
    """
    
    # Render the component
    components.html(
        html_template % json.dumps(mindmap_data),
        height=750,
        scrolling=True
    )
