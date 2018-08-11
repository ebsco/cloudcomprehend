import boto3
import xml.etree.cElementTree as ET
import math
import argparse
import os
import errno

#update this if deploying to lambda
LAMBDA_INVOCATION = False

# command line arguments
parser = argparse.ArgumentParser(description='VPC Network Visualizer')

# positional, required args
parser.add_argument('profile', help='aws profile')
parser.add_argument('region', help='aws region')
parser.add_argument('vpc', help='vpc id')

# value-based args
parser.add_argument('--outdir', dest='directory', help='output save directory', default="")
parser.add_argument('--stroke', dest='stroke', help='line stroke width', default=3, type=int)
parser.add_argument('--text', dest='line_height', help='text line height', default=20, type=int)
parser.add_argument('--subcols', dest='sub_cols', help='subnet alignment columns', default=3, type=int)
parser.add_argument('--peercols', dest='peer_cols', help='peer VPC alignment columns', default=1, type=int)
parser.add_argument('--fontl', dest='font_large', help='large font size', default=16, type=int)

# true/false args
parser.add_argument('--all', '-a', dest='all_resources', action='store_true', help='show non associated resources')
parser.add_argument('--linelabels', '-l', dest='labels', action='store_true', help='add connection labels')
parser.add_argument('--rtconnections', '-c', dest='rt_connections', action='store_true', help='add route table connections')

class DefaultLambdaNamespace:
    """Class that returns argparse-like default argument dict"""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

def get_configuration(lambda_invocation):
    """return arguments and authentication kwargs for given run configuration"""
    kwargs = {}
    if lambda_invocation:
        return (DefaultLambdaNamespace(all_resources=False,
                                       directory='',
                                       font_large=16,
                                       labels=False,
                                       line_height=20,
                                       peer_cols=1,
                                       profile='NONE',
                                       region='NONE',
                                       rt_connections=False,
                                       stroke=3,
                                       sub_cols=3,
                                       vpc='NONE'), kwargs)
    else:
        args = parser.parse_args()
        kwargs['profile_name'] = args.profile
        kwargs['region_name'] = args.region
        return (args, kwargs)

# parse cmd line args
(args, kwargs) = get_configuration(LAMBDA_INVOCATION)

SESSION = boto3.Session(**kwargs)

# draw.io specific resource shapes
ROUTE53_SHAPE = "mxgraph.aws3.route_53"
ROUTE_TABLE_SHAPE = "mxgraph.aws3.route_table"
INTERNET_GATEWAY_SHAPE = "mxgraph.aws3.internet_gateway"
ENI_SHAPE = "mxgraph.aws3.elastic_network_interface"
PEERING_SHAPE = "mxgraph.aws3.vpc_peering"
NAT_GATEWAY_SHAPE = "mxgraph.aws3.vpc_nat_gateway"
NACL_SHAPE = "mxgraph.aws3.network_access_controllist"
VPC_SHAPE = "mxgraph.aws3.virtual_private_cloud"
SUBNET_SHAPE = "mxgraph.aws3.permissions"
FLOW_LOGS_SHAPE = "mxgraph.aws3.flow_logs"
ENDPTS_SHAPE = "mxgraph.aws3.endpoints"
VPN_SHAPE = "mxgraph.aws3.vpn_gateway"
VPN_CONN_SHAPE = "mxgraph.aws3.vpn_connection"
GENERIC_SERVER_SHAPE = "mxgraph.aws3.traditional_server"
DIRECT_CONNECT_SHAPE = "mxgraph.aws3.direct_connect"
AWS_CLOUD_SHAPE = "mxgraph.aws3.cloud"

# colors
BLACK = "#000000"
GREEN = "#00ff00"
BLUE = "#0000ff"
RED = "#ff0000"

# aws icon specific colors
ICON_ORANGE = "#F58536"
AWS_BORDER_ORANGE = "#F59D56"
ICON_GOLD = "#D9A741"

# draw.io diagram dimensions
DIAGRAM_WIDTH = 4000
DIAGRAM_HEIGHT = 4000

# global padding dimension
PADDING = 60

# resource spacing
RESOURCE_DISTRIBUTION = PADDING * 3

# subnet minimum dimensions (if not associated with nat)
SUBNET_MIN_W = 340
SUBNET_MIN_H = 80

# vpc minimum dimensions (used to show peered vpcs)
VPC_MIN_W = 200
VPC_MIN_H = 120

# used for stacking peered vpc containers next to main diagram
VPC_PEER_COLS = args.peer_cols

# subnets are aligned according to associated nacl
SUBNET_ALIGNMENT_COLS = args.sub_cols

# space for route table listings and acl listings
VPC_GUTTER_DIM = 700

# add association labels to connections
CONNECTION_LABELS = args.labels

# diagram list column width
DIAGRAM_COL_WIDTH_SMALL = 70
DIAGRAM_COL_WIDTH_NORMAL = 120
DIAGRAM_COL_WIDTH_OVERSIZED = 210

# diagram line spacing
DIAGRAM_LINE_HEIGHT = args.line_height

# diagram list header spacing
DIAGRAM_HEADER_SPACING = 50

# small resource text offset for container
SMALL_RESOURCE_TEXT_OFFSET = 20

#connection weight
STROKE_WIDTH = args.stroke

# connections rounded: 0 for false, 1 for true
CONNECTIONS_ROUNDED = 1

# line bundle spacing
LINE_BUNDLE_SPACING = 10

# font sizes
FONT_SIZE_NORMAL = 12
FONT_SIZE_LARGE = args.font_large

# placeholders for connection organization
X_DIRECTION = 1
Y_DIRECTION = 0

# add route table connections to external resources (crowds diagram)
ADD_ROUTE_TABLE_CONNECTIONS = args.rt_connections

# only add route tables or nacls if they are associated with a subnet
OMIT_NON_ASSOCIATED_RESOURCES = not args.all_resources

# when determining a resource's human-friendly name, try this if 'Name' not present
SECOND_NAME_FIELD = 'aws:cloudformation:logical-id'

# used as a placeholder for adding horizontal lines to lists
HORIZONTAL_LINE = "horiz_line"

# used as an organization placeholder
NO_AZ = 'no_az'

# custom connection entries
CONNECTION_ENTRY_NONE = ""
CONNECTION_ENTRY_RIGHT = "entryX=1;entryY=0.5;"
CONNECTION_ENTRY_LEFT = "entryX=0;entryY=0.5;"

def create_xml_doc():
    return ET.Element("mxGraphModel",
                        dx="950",
                        dy="464",
                        grid="1",
                        gridSize="10",
                        guides="1",
                        tooltips="1",
                        connect="1",
                        arrows="1",
                        fold="1",
                        page="1",
                        pageScale="1",
                        pageWidth="{}".format(DIAGRAM_WIDTH),
                        pageHeight="{}".format(DIAGRAM_HEIGHT),
                        background="#ffffff",
                        math="0",
                        shadow="0")

def get_account_number():
    return SESSION.client('sts').get_caller_identity().get('Account')

def make_save_location(dir):
    if dir:
        try:
            os.makedirs(dir)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(dir):
                pass
            else:
                raise
    return os.path.join(dir, '')

def if_in(resource, *keys):
    #check for keys in map and return the value of the first one found
    for k in keys:
        if k in resource:
            return resource[k]
    return ""

def insert_text(xml_root, text, x, y, dx=15, dy=10, font_color=BLACK, font_size=FONT_SIZE_NORMAL):
    # add a text element
    newElement = ET.SubElement(xml_root, "mxCell",
        id="text-{}_{}".format(text, y),
        value="<font style='font-size: {}px'; color='{}'>{}</font>".format(font_size, font_color, text),
        vertex="1",
        style="text;html=1;labelBackgroundColor=#ffffff",
        parent="1")

    ET.SubElement(newElement, "mxGeometry",
        x="{}".format(x + dx),
        y="{}".format(y + dy),
        width="50",
        height="30").set('as','geometry')

def name_from_tags(resource):
    if 'Tags' in resource:
        for t in resource['Tags']:
            if t['Key'] == 'Name':
                return t['Value']
        for t_other in resource['Tags']:
            if t_other['Key'] == SECOND_NAME_FIELD:
                return t_other['Value']
        return ""
    else:
        return ""

def insert_line(xml_root, x1, y1, x2, y2):
    newElement = ET.SubElement(xml_root, "mxCell",
        id="line_{},{}_{},{}".format(x1, y1, x2, y2),
        value="",
        edge="1",
        style="shape=link;html=1;shadow=0;startArrow=diamondThin;startFill=1;endArrow=async;endFill=1;jettySize=auto;orthogonalLoop=1;strokeColor=#000000;strokeWidth=1;",
        parent="1")

    geometry = ET.SubElement(newElement, "mxGeometry",
        relative="1",
        width="50",
        height="50")

    geometry.set('as','geometry')

    ET.SubElement(geometry, "mxPoint",
                x="{}".format(x1),
                y="{}".format(y1)).set('as','sourcePoint')

    ET.SubElement(geometry, "mxPoint",
                x="{}".format(x2),
                y="{}".format(y2)).set('as','targetPoint')

class RouteGroup:
    def __init__(self, start_x_bundle, start_y_bundle, starting_direction, bundle_spacing=LINE_BUNDLE_SPACING, additional_break=-1):
        """RouteGroup takes a x coordinate to start stacking connections and a y coordinate to start stacking connections,
        either of these may be omitted by passing -1.  A RouteGroup object generates routes of (x,y) pairs and maintains the
        grouping by incrementing these stacking coordinates by the provided bundle spacing"""

        self.bundle_spacing = bundle_spacing
        self.current_x = start_x_bundle
        self.current_y = start_y_bundle
        self.starting_direction = starting_direction
        self.additional_break = additional_break

        if starting_direction != X_DIRECTION and starting_direction != Y_DIRECTION:
            # complex route will return as [] and not be used when rendering connections
            print("WARNING: bad starting direction {} for route group generator. \n(Use X_DIRECTION or Y_DIRECTION)".format(starting_direction))

    def get_next_route(self, origin_x, origin_y):
        complex_route = []
        if self.starting_direction == X_DIRECTION:
            complex_route.append((self.current_x, origin_y))
            if self.current_y != -1:
                complex_route.append((self.current_x, self.current_y))
            if self.additional_break != -1:
                complex_route.append((self.additional_break, self.current_y))

        elif self.starting_direction == Y_DIRECTION:
            complex_route.append((origin_x, self.current_y))
            if self.current_x != -1:
                complex_route.append((self.current_x, self.current_y))
            if self.additional_break != -1:
                complex_route.append((self.current_x, self.additional_break))

        if self.current_x != -1:
            self.current_x += self.bundle_spacing
        if self.current_y != -1:
            self.current_y -= self.bundle_spacing
        if self.additional_break != -1:
            self.additional_break -= self.bundle_spacing

        return complex_route

class DiagramContainer:
    """Generic diagram container"""
    def __init__(self, name, id, loc_x, loc_y, width, height, shape):
        self.name = name
        self.id = id
        self.loc_x = loc_x
        self.loc_y = loc_y
        self.width = width
        self.height = height
        self.shape = shape
        self.container_id = "{}_container".format(self.id)

    def get_container_id(self):
        return self.container_id

    def render_xml_connection(self, xml_root, other_id, text="", color=BLACK, stroke_width=STROKE_WIDTH, complex_route=[], connection_entry=CONNECTION_ENTRY_NONE):
        if CONNECTION_LABELS:
            label = text
        else:
            label = ""
        newElement = ET.SubElement(xml_root, "mxCell",
            id="connect{}to{}".format(self.id, other_id),
            style="edgeStyle=orthogonalEdgeStyle;rounded={};endArrow=async;strokeColor={};fillColor={};html=1;{}jettySize=auto;orthogonalLoop=1;strokeWidth={};".format(CONNECTIONS_ROUNDED,
                                                                                                                                                color, color, connection_entry, stroke_width),
            edge="1",
            value=label,
            parent="1",
            source="{}".format(self.container_id),
            target="{}".format(other_id))

        geometry = ET.SubElement(newElement, "mxGeometry", relative="1")
        geometry.set('as','geometry')

        if complex_route:
            array = ET.SubElement(geometry, "Array")
            array.set('as','points')
            for (x,y) in complex_route:
                ET.SubElement(array, "mxPoint", x="{}".format(x), y="{}".format(y))

    def render_xml(self, xml_root, icon_width=30, icon_height=36, icon_dx=20, icon_dy=-20, icon_color=ICON_ORANGE, arc_size=10):

        newElement_container = ET.SubElement(xml_root, "mxCell",
            id=self.container_id,
            value="",
            style="rounded=1;arcSize={};dashed=0;strokeColor=#000000;fillColor=none;gradientColor=none;strokeWidth=2;".format(arc_size),
            vertex="1",
            parent="1")

        ET.SubElement(newElement_container, "mxGeometry",
            x="{}".format(self.loc_x),
            y="{}".format(self.loc_y),
            width="{}".format(self.width),
            height="{}".format(self.height)).set('as','geometry')

        newElement = ET.SubElement(xml_root, "mxCell",
            id=self.id,
            value="",
            style="dashed=0;html=1;shape={};fillColor={};gradientColor=none;dashed=0;".format(self.shape, icon_color),
            vertex="1",
            parent="1")

        ET.SubElement(newElement, "mxGeometry",
                    x="{}".format(self.loc_x + icon_dx),
                    y="{}".format(self.loc_y + icon_dy),
                    width="{}".format(icon_width),
                    height="{}".format(icon_height)).set('as','geometry')

class DiagramObject:
    """Generic diagram object"""
    def __init__(self, name, id, loc_x, loc_y, shape, parent="1"):
        self.name = name
        self.id = id
        self.loc_x = loc_x
        self.loc_y = loc_y
        self.shape_id = shape
        self.parent = parent

    def render_xml(self, xml_root, width=50, height=50, icon_color=ICON_ORANGE):

        newElement = ET.SubElement(xml_root, "mxCell",
            id=self.id,
            value="",
            style="outlineConnect=0;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;shape={};fillColor={};gradientColor=none;".format(self.shape_id, icon_color),
            vertex="1",
            parent="{}".format(self.parent))

        ET.SubElement(newElement, "mxGeometry",
            x="{}".format(self.loc_x),
            y="{}".format(self.loc_y),
            width="{}".format(width),
            height="{}".format(height)).set('as','geometry')

    def get_id(self):
        return self.id

    def render_xml_connection(self, xml_root, other_id, text="", color=BLACK, stroke_width=STROKE_WIDTH, complex_route=[], connection_entry=CONNECTION_ENTRY_NONE):
        if CONNECTION_LABELS:
            label = text
        else:
            label = ""
        newElement = ET.SubElement(xml_root, "mxCell",
            id="connect{}to{}".format(self.id, other_id),
            style="edgeStyle=orthogonalEdgeStyle;rounded={};endArrow=async;strokeColor={};fillColor={};html=1;{}jettySize=auto;orthogonalLoop=1;strokeWidth={};".format(CONNECTIONS_ROUNDED,
                                                                                                                                                color, color, connection_entry, stroke_width),
            edge="1",
            value=label,
            parent="1",
            source="{}".format(self.id),
            target="{}".format(other_id))

        geometry = ET.SubElement(newElement, "mxGeometry", relative="1")
        geometry.set('as','geometry')

        if complex_route:
            array = ET.SubElement(geometry, "Array")
            array.set('as','points')
            for (x,y) in complex_route:
                ET.SubElement(array, "mxPoint", x="{}".format(x), y="{}".format(y))

class DiagramList:
    def __init__(self, title, id, list, fields, col_widths):
        self.title = title
        self.id = id
        self.list = list
        self.fields = fields
        self.lane_header_height = DIAGRAM_LINE_HEIGHT
        self.line_height = DIAGRAM_LINE_HEIGHT
        self.col_widths = col_widths
        self.header_spacing = DIAGRAM_HEADER_SPACING

    def create_lane(self, xml_root, x, width, height, section_title):
        """Create a column in the table"""
        lane_title = "{}_{}".format(self.title, section_title)
        newElement = ET.SubElement(xml_root, "mxCell",
            id=lane_title,
            value=section_title,
            style="swimlane;html=1;startSize=20;",
            vertex="1",
            parent="{}".format(self.id))

        ET.SubElement(newElement, "mxGeometry",
            x="{}".format(x),
            y="{}".format(self.lane_header_height),
            width="{}".format(width),
            height="{}".format(height)).set('as','geometry')

        return lane_title

    def add_entry(self, xml_root, lane, value, y_offset, width):
        """add an entry to a table"""
        newElement = ET.SubElement(xml_root, "mxCell",
            id="{}_{}_{}".format(lane, value, y_offset),
            value="{}".format(value),
            style="text;strokeColor=none;fillColor=none;align=left;verticalAlign=top;spacingLeft=4;spacingRight=4;overflow=hidden;rotatable=0;points=[[0,0.5],[1,0.5]];portConstraint=eastwest;",
            vertex="1",
            parent="{}".format(lane))

        ET.SubElement(newElement, "mxGeometry",
            x="5",
            y="{}".format(y_offset),
            width="{}".format(width - 10),
            height="26").set('as','geometry')

    def render_xml_connection(self, xml_root, other_id, text="", color=BLACK, stroke_width=STROKE_WIDTH, complex_route=[]):
        if CONNECTION_LABELS:
            label = text
        else:
            label = ""
        newElement = ET.SubElement(xml_root, "mxCell",
            id="connect{}to{}".format(self.id, other_id),
            style="edgeStyle=orthogonalEdgeStyle;rounded={};endArrow=async;strokeColor={};fillColor={};html=1;jettySize=auto;orthogonalLoop=1;strokeWidth={};".format(CONNECTIONS_ROUNDED,
                                                                                                                                                                    color, color, stroke_width),
            edge="1",
            value=label,
            parent="1",
            source="{}".format(self.id),
            target="{}".format(other_id))

        geometry = ET.SubElement(newElement, "mxGeometry", relative="1")
        geometry.set('as','geometry')

        if complex_route:
            array = ET.SubElement(geometry, "Array")
            array.set('as','points')
            for (x,y) in complex_route:
                ET.SubElement(array, "mxPoint", x="{}".format(x), y="{}".format(y))

    def render_xml(self, xml_root, x, y):
        width = 0
        for col_width in self.col_widths:
            width += col_width
        height = self.header_spacing + (self.line_height * len(self.list))
        newElement = ET.SubElement(xml_root, "mxCell",
            id="{}".format(self.id),
            value="{}".format(self.title),
            style="swimlane;html=1;childLayout=stackLayout;resizeParent=1;resizeParentMax=0;startSize=20;",
            vertex="1",
            parent="1")

        ET.SubElement(newElement, "mxGeometry",
            x="{}".format(x),
            y="{}".format(y),
            width="{}".format(width),
            height="{}".format(height)).set('as','geometry')

        lanes = []
        lane_x = 0
        for f in range(len(self.fields)):
            lanes.append(self.create_lane(xml_root, lane_x, self.col_widths[f], height - self.lane_header_height, self.fields[f]))
            lane_x += self.col_widths[f]

        y_offset = self.line_height
        for entry in self.list:
            # check for horizontal line placeholder
            if entry == HORIZONTAL_LINE:
                horiz_line_y = y + y_offset + int(self.header_spacing / 2) + 5
                insert_line(xml_root, x, horiz_line_y,
                            x + width, horiz_line_y)
            else:
                for i in range(len(entry)):
                    self.add_entry(xml_root, lanes[i], entry[i], y_offset, self.col_widths[i])
            y_offset += self.line_height

        return height

class DirectConnectResource:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.associations = []

    def add_association(self, assoc):
        self.associations.append(assoc)

    def render_xml(self, xml_root, x, y, padding=PADDING):
        dc_object = DiagramObject(self.id, self.id, x, y, DIRECT_CONNECT_SHAPE)
        dc_object.render_xml(xml_root, height=60)

        insert_text(xml_root, "{}".format(self.name), x, y, dx=50, dy=0)
        insert_text(xml_root, "{}".format(self.id), x, y + DIAGRAM_LINE_HEIGHT, dx=50, dy=0)

        # add connections to registered associations
        for assoc in self.associations:
            dc_object.render_xml_connection(xml_root, "{}".format(assoc), color=RED)

class NAclResource:
    def __init__(self, id, name):
        self.id = id
        self.col_suggestion = 0
        self.rules_ingress = []
        self.rules_egress = []
        self.name = name
        self.x = 0

    def get_id(self):
        return self.id

    def add_rule(self, rule_number, protocol, egress, cidr_block, rule_action):
        if egress:
            self.rules_egress.append((int(rule_number), protocol, egress, cidr_block, rule_action))
        else:
            self.rules_ingress.append((int(rule_number), protocol, egress, cidr_block, rule_action))

    def add_col_suggestion(self, suggestion):
        self.col_suggestion = suggestion

    def get_col_suggestion(self):
        return self.col_suggestion

    def get_x(self):
        return self.x

    def render_xml(self, xml_root, x, y, route_generator, padding=PADDING):
        self.x = x
        nacl_object = DiagramObject(self.id, self.id, x, y, NACL_SHAPE)
        nacl_object.render_xml(xml_root)

        insert_text(xml_root, "{}".format(self.id), x, y, dx=-30, dy=50)

        sorted_rules_egress = sorted(self.rules_egress, key=lambda rule: rule[0])
        sorted_rules_ingress = sorted(self.rules_ingress, key=lambda rule: rule[0])

        #add horizontal line separator
        sorted_rules_egress.append(HORIZONTAL_LINE)
        sorted_rules_egress.extend(sorted_rules_ingress)

        fields = ["Rule Number", "Protocol", "Egress", "Cidr Block", "Rule Action"]
        widths = [DIAGRAM_COL_WIDTH_NORMAL, DIAGRAM_COL_WIDTH_SMALL, DIAGRAM_COL_WIDTH_SMALL,
                  DIAGRAM_COL_WIDTH_OVERSIZED, DIAGRAM_COL_WIDTH_SMALL]

        if len(sorted_rules_egress) > 0:
            label = "{}  |  {}".format(self.name, self.id)
            if self.name == "":
                label = self.id

            DiagramList("{}".format(label),
                        "{}_list".format(self.id),
                        sorted_rules_egress,
                        fields,
                        widths).render_xml(xml_root, int((x - VPC_GUTTER_DIM) * 3.5) - int(1.5 * VPC_GUTTER_DIM), padding)

        nacl_object.render_xml_connection(xml_root, "{}_list".format(self.id), color=RED,
                                          complex_route=route_generator.get_next_route(x + 30, y))

class NgResource:
    def __init__(self, id, subnet_id, name):
        self.id = id
        self.subnet_id = subnet_id
        self.name = name
        self.igw = None

    def get_id(self):
        return self.id

    def get_subnet_id(self):
        return self.subnet_id

    def register_igw(self, igw_id):
        self.igw = igw_id

    def render_xml(self, xml_root, x, y, padding=PADDING):
        ng_object = DiagramObject(self.id, self.id, x, y, NAT_GATEWAY_SHAPE)
        ng_object.render_xml(xml_root)

        insert_text(xml_root,"{}".format(self.name), x, y, dx=50, dy=0)
        insert_text(xml_root,"{}".format(self.id), x, y + DIAGRAM_LINE_HEIGHT, dx=50, dy=0)

        if self.igw != None:
            ng_object.render_xml_connection(xml_root, self.igw, color=BLUE, complex_route=[(x + (4 * PADDING), y + PADDING)])

class FlowLogsResource:
    def __init__(self, id, name):
        self.id = id
        self.name = name

    def get_id(self):
        return self.id

    def render_xml(self, xml_root, x, y, padding=PADDING):
        fl_object = DiagramObject(self.id, self.id, x, y, FLOW_LOGS_SHAPE)
        fl_object.render_xml(xml_root, width=30, height=30)

        insert_text(xml_root, "{}".format(self.name), x, y, dx=-10, dy=5)
        insert_text(xml_root, "{}".format(self.id), x, y + DIAGRAM_LINE_HEIGHT, dx=-10, dy=5)

class VpcEndpointResource:
    def __init__(self, service_name, type):
        self.ids = []
        self.service_name = service_name
        self.type = type
        self.rt_associations = []

    def add_vpce_id(self, new_id):
        #for repeated vpce ids for resource endpoints
        self.ids.append(new_id)

    def get_servicename(self):
        return self.service_name

    def register_rt_association(self, rt_id):
        self.rt_associations.append(rt_id)

    def render_xml(self, xml_root, x, y, route_generator, padding=PADDING):
        vpc_e_object = DiagramObject(self.service_name, self.service_name, x, y, ENDPTS_SHAPE)
        vpc_e_object.render_xml(xml_root)
        insert_text(xml_root,"{} {}".format(self.service_name, self.type), x, y, dx=50, dy=0)

        # add text for added vpce's
        id_y = y + DIAGRAM_LINE_HEIGHT
        for id in self.ids:
            insert_text(xml_root,"{}".format(id), x, id_y, dx=50, dy=0)
            id_y += DIAGRAM_LINE_HEIGHT

        # add associations
        for assoc in self.rt_associations:
            vpc_e_object.render_xml_connection(xml_root,"{}".format(assoc), color=BLUE,
                                complex_route=route_generator.get_next_route(x, y + 30))

class VpnGatewayResource:
    def __init__(self, id, name, vpn):
        self.id = id
        self.name = name
        self.vpn = vpn

    def get_id(self):
        return self.id

    def render_xml(self, xml_root, x, y, padding=PADDING):
        vpngw_object = DiagramObject(self.id, self.id, x, y, VPN_SHAPE)
        vpngw_object.render_xml(xml_root)

        if self.vpn != "":
            #add vpn resource
            vpn_object = DiagramObject(self.vpn, self.vpn, x + (3 * padding), y, VPN_CONN_SHAPE)
            vpn_object.render_xml(xml_root)

            vpn_object.render_xml_connection(xml_root,self.id)
            insert_text(xml_root,"{}".format(self.vpn), x + (3 * padding), y, dx=80, dy=20)

        insert_text(xml_root,"{}".format(self.name), x, y, dx=50, dy=0)
        insert_text(xml_root,"{}".format(self.id), x, y + DIAGRAM_LINE_HEIGHT, dx=50, dy=0)

class SubnetResource:
    def __init__(self, id, cidr, az, name):
        self.id = id
        self.cidr = cidr
        self.az = az
        self.ng_list = []
        self.col_suggestion = 0
        self.associations = []
        self.name = name

    def get_dimensions(self):
        h = SUBNET_MIN_H
        ng_height_requirement = len(self.ng_list) * RESOURCE_DISTRIBUTION - PADDING
        if ng_height_requirement > h:
            h = ng_height_requirement
        return (SUBNET_MIN_W, h)

    def register_ng(self, ng_resource):
        self.ng_list.append(ng_resource)

    def register_nacl_association(self, assoc_data):
        self.associations.append(assoc_data)

    def get_col_suggestion(self):
        if len(self.associations) > 0:
            return self.associations[0][3].get_col_suggestion()
        else:
            return 0

    def get_id(self):
        return self.id

    def get_az(self):
        return self.az

    def get_name(self):
        return self.name

    def render_xml(self, xml_root, x, y, route_generator, padding=PADDING):
        (subnet_w, subnet_h) = self.get_dimensions()
        subnet_container = DiagramContainer(self.id, self.id,
                                            x, y,
                                            subnet_w, subnet_h, SUBNET_SHAPE)

        subnet_container.render_xml(xml_root,icon_color=ICON_GOLD)
        insert_text(xml_root,"{}, CIDR: {}".format(self.id, self.cidr), x, y)
        insert_text(xml_root,"{}".format(self.name), x, y + DIAGRAM_LINE_HEIGHT)

        for a in self.associations:
            subnet_container.render_xml_connection(xml_root,"{}".format(a[1]), text=a[2], color=GREEN,
                        complex_route=route_generator.get_next_route(x, y + 30),
                        connection_entry=CONNECTION_ENTRY_RIGHT)

        ng_x = x + subnet_w - int(padding / 2)
        ng_y = y + int(subnet_h / 2)
        for ng in self.ng_list:
            ng.render_xml(xml_root,ng_x, ng_y)
            ng_y += RESOURCE_DISTRIBUTION

class IgwResource:
    def __init__(self, id, vpc_id, name):
        self.id = id
        self.vpc_id = "{}_container".format(vpc_id)
        self.name = name

    def get_id(self):
        return self.id

    def render_xml(self, xml_root, x, y, padding=PADDING, shape=INTERNET_GATEWAY_SHAPE):
        igw_object = DiagramObject(self.id, self.id, x, y, shape)
        igw_object.render_xml(xml_root)

        insert_text(xml_root,"{}".format(self.name), x, y, dx=50, dy=0)
        insert_text(xml_root,"{}".format(self.id), x, y + DIAGRAM_LINE_HEIGHT, dx=50, dy=0)

class NetworkInterfaceResource:
    def __init__(self, id, subnet_id, type):
        """CURRENTLY UNUSED IN THE SCRIPT"""
        self.id = id
        self.subnet_id = "{}_container".format(subnet_id)
        self.type = type

    def get_id(self):
        return self.id

    def render_xml(self, xml_root, x, y, width, height, padding=PADDING):
        igw_object = DiagramObject(self.id, self.id, x, y, ENI_SHAPE)
        igw_object.render_xml(xml_root)

        igw_object.render_xml_connection(xml_root,self.subnet_id, text=self.type, COLOR=BLUE)
        insert_text(xml_root,"{}".format(self.id), x, y, dx=0, dy=50)

class RouteTableResource:
    def __init__(self, id, name):
        self.id = id
        self.associations = []
        self.routes = []
        self.name = name
        self.az_connections = []

    def get_id(self):
        return self.id

    def cmp_cidr(self, cidr_one_list, cidr_two_list):
        if not cidr_one_list or not cidr_two_list:
            #both values are the same
            return 0
        try:
            #try to parse as an integer
            val_one = int(cidr_one_list[0])
        except:
            return -1
        try:
            #try to parse as an integer
            val_two = int(cidr_two_list[0])
        except:
            return 1
        if val_one < val_two:
            return -1
        elif val_one > val_two:
            return 1
        else:
            #recursively compare the next bytes of each cidr block
            return self.cmp_cidr(cidr_one_list[1:], cidr_two_list[1:])

    def sort_routes(self):
        #sort cidr blocks
        cidr_sorted = sorted(self.routes, cmp=lambda cidr_one,cidr_two:
                                                self.cmp_cidr(cidr_one.split("."), cidr_two.split(".")),
                                          key=lambda cidr: cidr[0])
        #add local gw to front of list
        for r in range(len(cidr_sorted)):
            if cidr_sorted[r][2] == 'local':
                cidr_sorted.insert(0, cidr_sorted.pop(r))
        return cidr_sorted

    def register_rt_association(self, subnet_id, rt_assoc_id, az):
        self.associations.append((subnet_id, rt_assoc_id))
        self.az_connections.append(az)

    def get_suggested_az(self):
        if not self.az_connections:
            return NO_AZ
        else:
            return max(set(self.az_connections), key=self.az_connections.count)

    def simplify_origin(self, origin):
        if origin == 'EnableVgwRoutePropagation':
            return 'Propagated'
        elif origin == 'CreateRoute':
            return 'Create Route'
        elif origin == 'CreateRouteTable':
            return 'Create Table'
        else:
            return origin

    def add_route(self, dest_cidr, state, gw_id, origin):
        self.routes.append((dest_cidr, state, gw_id, self.simplify_origin(origin)))

    def render_xml(self, xml_root, x, y, list_y, route_generator, list_route_generator, rt_diagram_route_generator, padding=PADDING):
        route_table_diagram = DiagramObject(self.id, self.id, x, y, ROUTE_TABLE_SHAPE)
        route_table_diagram.render_xml(xml_root)
        insert_text(xml_root, self.id, x, y, dx=0, dy=50)

        for assoc in self.associations:
            route_table_diagram.render_xml_connection(xml_root, "{}_container".format(assoc[0]), text=assoc[1],
                                            complex_route=route_generator.get_next_route(x + 50, y + 40))

        if len(self.routes) > 0:
            #list fields and lane widths
            fields = ["Destination CIDR", "State", "Gateway ID", "Origin"]
            widths = [DIAGRAM_COL_WIDTH_OVERSIZED, DIAGRAM_COL_WIDTH_SMALL, DIAGRAM_COL_WIDTH_NORMAL, DIAGRAM_COL_WIDTH_NORMAL]

            label = "{}  |  {}".format(self.name, self.id)
            if self.name == "":
                label = self.id

            sorted_routes = self.sort_routes()

            rt_list = DiagramList("{}".format(label),
                            "{}_list".format(self.id), sorted_routes, fields, widths)
            resource_height = rt_list.render_xml(xml_root, 0, list_y - RESOURCE_DISTRIBUTION)

            if ADD_ROUTE_TABLE_CONNECTIONS:
                routes_connected = []
                route_y = y + padding
                for route in self.routes:
                    if route[2] not in routes_connected:
                        rt_list.render_xml_connection(xml_root, route[2], complex_route=rt_diagram_route_generator.get_next_route(x, route_y))
                        routes_connected.append(route[2])
                        route_y += LINE_BUNDLE_SPACING

        route_table_diagram.render_xml_connection(xml_root, "{}_list".format(self.id), color=RED,
                                                    complex_route=list_route_generator.get_next_route(x, y + 10),
                                                    connection_entry=CONNECTION_ENTRY_RIGHT)
        return resource_height

class AZResource:
    def __init__(self, id):
        self.id = id
        self.subnets = []
        self.width_override = (False, 0)

    def register_subnet(self, subnet_resource):
        self.subnets.append(subnet_resource)

    def get_id(self):
        return self.id

    def override_width(self, width):
        self.width_override = (True, width)

    def empty(self):
        return len(self.subnets) == 0

    def get_total_subnets(self):
        return len(self.subnets)

    def get_dimensions(self):
        w = 0
        h = PADDING
        for subnet in self.subnets:
            (new_w, new_h) = subnet.get_dimensions()
            w = new_w
            h += new_h + PADDING
        if self.width_override[0]:
            w = self.width_override[1]
        else:
            w = w + (2 * PADDING)
        return (w, h)

    def render_xml(self, xml_root, x, y, nacl_route_generator, padding=PADDING):
        #render az outline
        (width, height) = self.get_dimensions()

        #add a box with a dashed outline
        newElement = ET.SubElement(xml_root, "mxCell",
            id=self.id,
            style="rounded=1;arcSize=10;dashed=1;strokeColor={};fillColor=none;gradientColor=none;dashPattern=8 4;strokeWidth=2;".format(AWS_BORDER_ORANGE),
            vertex="1",
            value="",
            parent="1")

        ET.SubElement(newElement, "mxGeometry",
            x="{}".format(x),
            y="{}".format(y),
            width="{}".format(width),
            height="{}".format(height)).set('as','geometry')

        insert_text(xml_root, self.id, x + int(width / 2) - 40, y + height - 40, font_color=AWS_BORDER_ORANGE)

        subnet_x = x + padding
        subnet_y = y + padding

        sorted_subnets = sorted(self.subnets, key=lambda subnet_obj: subnet_obj.get_name())

        for subnet in sorted_subnets:
            col_suggestion = subnet.get_col_suggestion()
            (sub_w, sub_h) = subnet.get_dimensions()
            offset = col_suggestion * ((width - sub_w - padding) / SUBNET_ALIGNMENT_COLS)
            subnet.render_xml(xml_root, subnet_x + offset, subnet_y, nacl_route_generator)
            subnet_y = subnet_y + padding + sub_h

class PeeringResource:
    def __init__(self, id, accepting_vpc, requesting_vpc, name, connection_ref):
        self.id = id
        self.accepting_vpc = accepting_vpc
        self.requesting_vpc = requesting_vpc
        self.name = name
        self.connection = connection_ref

    def register_diagram_vpc(self, diagram_vpc_id):
        self.diagram_vpc_id = diagram_vpc_id

    def get_id(self):
        return self.id

    def render_xml(self, xml_root, x, y, route_generator, padding=PADDING):
        peering_object = DiagramObject(self.id, self.id, x, y, PEERING_SHAPE)
        peering_object.render_xml(xml_root)

        peering_object.render_xml_connection(xml_root, self.connection, complex_route=route_generator.get_next_route(x + 50, y + 40))
        insert_text(xml_root, "{}".format(self.name), x, y, dx=50, dy=-10)
        insert_text(xml_root, "{}".format(self.id), x, y + DIAGRAM_LINE_HEIGHT, dx=50, dy=-10)

class VpcResource:
    def __init__(self, id, name, cidr):
        self.id = id
        self.az_list = []
        self.nacl_list = []
        self.rt_list = []
        self.name = name
        self.cidr = cidr
        self.dns_server_list = []
        self.domain_list = []

    def register_az(self, az_resource):
        self.az_list.append(az_resource)

    def get_container_id(self):
        return "{}_container".format(self.id)

    def register_nacl(self, nacl_resource):
        self.nacl_list.append(nacl_resource)

    def register_rt(self, rt_resource):
        self.rt_list.append(rt_resource)

    def check_empty(self):
        return not self.az_list and not self.nacl_list and not self.rt_list

    def add_dns_servers_from_opts(self, dns_server_list):
        self.dns_server_list = dns_server_list

    def add_domains_from_opts(self, domain_list):
        self.domain_list = domain_list

    def sort_rt_resources(self):
        if self.check_empty():
            return []
        else:
            az_sorting_list = list(map(lambda az: az.get_id(), self.az_list))
            az_sorting_list.append(NO_AZ)
            return sorted(self.rt_list, cmp=lambda rt_one,rt_two: cmp(az_sorting_list.index(rt_one.get_suggested_az()),
                                                                      az_sorting_list.index(rt_two.get_suggested_az())))

    def get_dimensions(self):
        """Determine dimensions based on registered components"""
        if self.check_empty():
            return (VPC_MIN_W, VPC_MIN_H)

        az_combined_height_requirement = RESOURCE_DISTRIBUTION + (2 * PADDING)
        az_max_width_requirement = RESOURCE_DISTRIBUTION + PADDING

        for az in self.az_list:
            (w, h) = az.get_dimensions()
            az_combined_height_requirement += h
            if w + PADDING > az_max_width_requirement:
                az_max_width_requirement = w + PADDING

        nacl_combined_width_requirement = len(self.nacl_list) * RESOURCE_DISTRIBUTION

        if nacl_combined_width_requirement > az_max_width_requirement:
            az_max_width_requirement = nacl_combined_width_requirement
            for az in self.az_list:
                az.override_width(az_max_width_requirement - PADDING)

        rt_combined_height_requirement = len(self.rt_list) * RESOURCE_DISTRIBUTION

        if rt_combined_height_requirement > az_combined_height_requirement:
            az_combined_height_requirement = rt_combined_height_requirement

        return (az_max_width_requirement + (5 * PADDING),
                az_combined_height_requirement + (2 * PADDING))

    def render_xml(self, xml_root, x, y, padding=PADDING, vpc_height_override=0):
        #account for nacl and rt row/col
        (vpc_width, vpc_height) = self.get_dimensions()
        vpc_x = x
        vpc_y = y

        vpc_height = max(vpc_height, vpc_height_override)

        vpc_container = DiagramContainer(self.id, self.id,
                                         vpc_x, vpc_y,
                                         vpc_width, vpc_height, VPC_SHAPE)
        small_vpc = False #used for displaying peered vpcs in main diagram
        text_offset = 50
        if self.check_empty():
            text_offset = SMALL_RESOURCE_TEXT_OFFSET
            small_vpc = True

        vpc_container.render_xml(xml_root, icon_width=55, icon_dx=text_offset, arc_size=6)
        insert_text(xml_root, self.name, x, y, dx=text_offset, dy=20)
        insert_text(xml_root, self.id, x, y + DIAGRAM_LINE_HEIGHT, dx=text_offset, dy=20)
        insert_text(xml_root, self.cidr, x, y + (2 * DIAGRAM_LINE_HEIGHT), dx=text_offset, dy=20)

        if not small_vpc:
            insert_text(xml_root, "Domain Names", x, y + (3 * DIAGRAM_LINE_HEIGHT), dx=text_offset, dy=20)
            list_y = y + (4 * DIAGRAM_LINE_HEIGHT)
            for dn in self.domain_list:
                insert_text(xml_root, "- {}".format(dn), x, list_y, dx=text_offset, dy=20)
                list_y += DIAGRAM_LINE_HEIGHT

            insert_text(xml_root, "Domain Name Servers", x, list_y, dx=text_offset, dy=20)
            list_y += DIAGRAM_LINE_HEIGHT
            for dns in self.dns_server_list:
                insert_text(xml_root,"- {}".format(dns), x, list_y, dx=text_offset, dy=20)
                list_y += DIAGRAM_LINE_HEIGHT

        nacl_x = vpc_x + RESOURCE_DISTRIBUTION + (2 * padding)
        nacl_y = vpc_y + padding
        nacl_list_route_generator = RouteGroup(-1, y - (2 * padding), Y_DIRECTION)

        for nacl in self.nacl_list:
            nacl.render_xml(xml_root, nacl_x, nacl_y, nacl_list_route_generator)
            nacl_x += RESOURCE_DISTRIBUTION

        rt_x = vpc_x + int(padding / 2)
        rt_y = vpc_y + RESOURCE_DISTRIBUTION + padding
        rt_list_y = rt_y
        rt_height = 0

        rt_route_generator = RouteGroup(x + (2 * padding), -1, X_DIRECTION)
        rt_list_route_generator = RouteGroup(x - 3 * padding, -1, X_DIRECTION)
        rt_gw_resource_route_generator = RouteGroup((5 * -padding),
                                                    vpc_y + vpc_height + VPC_GUTTER_DIM,
                                                    X_DIRECTION,
                                                    additional_break=vpc_x + vpc_width + VPC_GUTTER_DIM)

        for rt in self.sort_rt_resources():
            rt_height = rt.render_xml(xml_root, rt_x, rt_y, rt_list_y, rt_route_generator, rt_list_route_generator, rt_gw_resource_route_generator)
            rt_list_y += max(padding + rt_height, RESOURCE_DISTRIBUTION)
            rt_y += max(int(rt_height / 1.3), RESOURCE_DISTRIBUTION)

        az_x = vpc_x + RESOURCE_DISTRIBUTION
        az_y = vpc_y + RESOURCE_DISTRIBUTION

        small_az_width = int((vpc_width - (7 * padding)) / 2)
        right = False

        total_subnets = 0
        for az_resource_subnets in self.az_list:
            total_subnets += az_resource_subnets.get_total_subnets()

        nacl_route_generator = RouteGroup((vpc_width + vpc_x - padding) - (total_subnets * LINE_BUNDLE_SPACING),
                                          (vpc_y + (2 * padding)) + (total_subnets * LINE_BUNDLE_SPACING),
                                          X_DIRECTION)

        for az in self.az_list:
            if az.empty():
                az.override_width(small_az_width)
                if right:
                    az.render_xml(xml_root, az_x + small_az_width + padding, az_y, None)
                    az_y = az_y + padding + az.get_dimensions()[1]
                else:
                    az.render_xml(xml_root, az_x, az_y, None)
                right = not right
            else:
                if right: #a previous az was empty
                    az_y += SUBNET_MIN_H + padding
                    right = False
                az.render_xml(xml_root, az_x, az_y, nacl_route_generator)
                az_y = az_y + padding + az.get_dimensions()[1]

class RegionResource:
    def __init__(self, region_name):
        self.region_name = region_name
        self.width = 0
        self.height = 0

    def register_vpc(self, vpc_resource):
        self.vpc = vpc_resource

    def get_dimensions(self, region_height_override=0, padding=PADDING):
        (vpc_width, vpc_height) = self.vpc.get_dimensions()
        width = vpc_width + (2 * padding)
        height = max(vpc_height, region_height_override) + (2 * padding)
        return (width, height)

    def render_xml(self, xml_root, x, y, padding=PADDING, region_height_override=0):

        (self.width, self.height) = self.get_dimensions(region_height_override=region_height_override)

        newElement = ET.SubElement(xml_root, "mxCell",
            id="{}".format(self.region_name),
            style="rounded=1;arcSize=6;dashed=1;strokeColor=#000000;fillColor=none;gradientColor=none;dashPattern=8 4;strokeWidth=2;",
            value="",
            vertex="1",
            parent="1")

        ET.SubElement(newElement, "mxGeometry",
            x="{}".format(x),
            y="{}".format(y),
            width="{}".format(self.width),
            height="{}".format(self.height)).set('as','geometry')

        insert_text(xml_root,self.region_name, x + int(self.width / 2) - 40, y + self.height - 40, font_size=FONT_SIZE_LARGE)

        self.vpc.render_xml(xml_root, x + padding, y + padding, vpc_height_override=self.height - (2 * padding))

        #return y coordinate of bottom of resource
        return x + self.height

class AccountResource:
    def __init__(self, profile):
        self.profile = profile
        self.account_number = get_account_number()
        self.width = 0
        self.height = 0

    def set_dimensions(self, w, h):
        self.width = w
        self.height = h

    def render_xml(self, xml_root, x, y, padding=PADDING):
        account_container = DiagramContainer(self.account_number, self.account_number,
                        x, y, self.width, self.height, AWS_CLOUD_SHAPE)
        account_container.render_xml(xml_root, icon_width=55, icon_dx=50, arc_size=2)
        insert_text(xml_root, self.profile, x, y, dx=50, dy=20, font_size=FONT_SIZE_LARGE)
        insert_text(xml_root, self.account_number, x, y + DIAGRAM_LINE_HEIGHT, dx=50, dy=20,font_size=FONT_SIZE_LARGE)

def visualize_vpc(ec2, region, current_vpc, name, vpc_cidr, dhcp_opts_id, dir, profile, xml_doc):
    """IN: ec2 boto3 client, region name, vpc name (id), vpc name from tags, vpc cidr value, dhcp options id, dir to write to
       OUT: filename that xml doc was written to"""

    # anon. fn definitions
    # check if a given resource is in the current vpc
    in_vpc = lambda resource: if_in(resource, 'VpcId') == current_vpc

    # required xml boilerplate
    xml_root = ET.SubElement(xml_doc, "root")
    ET.SubElement(xml_root, "mxCell", id="0")
    ET.SubElement(xml_root, "mxCell", id="1", parent="0")

    #initial resource lists (These are used to store objects created with data from calls to boto3)
    #after creating objects and determining any associations between them, the code for rendering
    #the xml for these objects iterates over these lists
    az_resources = []
    rt_resources = []
    nacl_resources = []
    subnet_resources = []
    ng_resources = []
    igw_resources = []
    peering_resources = []
    flow_logs_resources = []
    endpoints_resources = []
    vpn_gw_resources = []
    peer_vpc_resources = []
    dhcp_opt_dns_servers = []
    dhcp_opt_domains = []
    egress_gateway_resources = []
    vpn_conn_resources = []
    direct_connect_resources = []
    nacl_association_data = []

    #load from client
    for az in ec2.describe_availability_zones()['AvailabilityZones']:
        az_resources.append(AZResource(az['ZoneName']))

    for ng in ec2.describe_nat_gateways()['NatGateways']:
        if in_vpc(ng):
            ng_resources.append(NgResource(ng['NatGatewayId'], ng['SubnetId'], name_from_tags(ng)))

    for subnet in ec2.describe_subnets()['Subnets']:
        subnet_az = subnet['AvailabilityZone']
        subnet_id = subnet['SubnetId']
        if in_vpc(subnet):
            for az in az_resources:
                # for subnet az
                if az.get_id() == subnet_az:
                    new_subnet_resource = SubnetResource(subnet_id, subnet['CidrBlock'], subnet_az, name_from_tags(subnet))
                    az.register_subnet(new_subnet_resource)
                    for ng in ng_resources:
                        if ng.get_subnet_id() == subnet_id:
                            #add ng to subnet
                            new_subnet_resource.register_ng(ng)
                    subnet_resources.append(new_subnet_resource)
                    break

    for rt in ec2.describe_route_tables()['RouteTables']:
        if in_vpc(rt):
            new_rt_resource = RouteTableResource(rt['RouteTableId'], name_from_tags(rt))
            rt_subnet_associated = False
            for assoc in rt['Associations']:
                if 'SubnetId' in assoc:
                    rt_subnet_az = ""
                    for subnet_az in subnet_resources:
                        if assoc['SubnetId'] == subnet_az.get_id():
                            rt_subnet_az = subnet_az.get_az()
                    rt_subnet_associated = True
                    new_rt_resource.register_rt_association(assoc['SubnetId'], assoc['RouteTableAssociationId'], rt_subnet_az)
            for route in rt['Routes']:
                #look for available data
                cidr = ""
                if 'DestinationCidrBlock' in route:
                    cidr = route['DestinationCidrBlock']
                else:
                    current_prefix = route['DestinationPrefixListId']
                    for prefix in ec2.describe_prefix_lists()['PrefixLists']:
                        if prefix['PrefixListId'] == current_prefix:
                            cidr = prefix['PrefixListName']
                state = if_in(route, 'State')
                origin = if_in(route, 'Origin')
                gw_id = if_in(route, 'GatewayId', 'NetworkInterfaceId', 'VpcPeeringConnectionId')
                new_rt_resource.add_route(cidr, state, gw_id, origin)

            #add if associated or set to add resources without associations
            if rt_subnet_associated or not OMIT_NON_ASSOCIATED_RESOURCES:
                rt_resources.append(new_rt_resource)

    for nacl in ec2.describe_network_acls()['NetworkAcls']:
        if in_vpc(nacl):
            new_nacl_resource = NAclResource(nacl['NetworkAclId'], name_from_tags(nacl))
            for subnet_association in nacl['Associations']:
                nacl_association_data.append((subnet_association['SubnetId'],
                                              nacl['NetworkAclId'],
                                              subnet_association['NetworkAclAssociationId'],
                                              new_nacl_resource, new_nacl_resource))
            for rule in nacl['Entries']:
                new_nacl_resource.add_rule(rule['RuleNumber'], rule['Protocol'],
                                           rule['Egress'], rule['CidrBlock'],
                                           rule['RuleAction'])

            if nacl['Associations'] or not OMIT_NON_ASSOCIATED_RESOURCES:
                nacl_resources.append(new_nacl_resource)

    for igw in ec2.describe_internet_gateways()['InternetGateways']:
        for attached in igw['Attachments']:
            if in_vpc(attached):
                igw_resources.append(IgwResource(igw['InternetGatewayId'], current_vpc, name_from_tags(igw)))
                for ng_igw in ng_resources:
                    ng_igw.register_igw(igw['InternetGatewayId'])

    for peering in ec2.describe_vpc_peering_connections()['VpcPeeringConnections']:
        requesting_vpc = peering['RequesterVpcInfo']['VpcId']
        accepting_vpc = peering['AccepterVpcInfo']['VpcId']
        if requesting_vpc == current_vpc or accepting_vpc == current_vpc:

            if requesting_vpc == current_vpc:
                relation_type = 'AccepterVpcInfo'
            else:
                relation_type = 'RequesterVpcInfo'

            peer_cidr = peering[relation_type]['CidrBlock']
            peer_name = "Account: {}".format(peering[relation_type]['OwnerId'])
            peer_vpc_id = peering[relation_type]['VpcId']

            peer_vpc_resources.append(VpcResource(peer_vpc_id, peer_name, peer_cidr))

            new_peering_resource = PeeringResource(peering['VpcPeeringConnectionId'],
                                                   accepting_vpc,
                                                   requesting_vpc,
                                                   name_from_tags(peering),
                                                   "{}_container".format(peer_vpc_id))

            new_peering_resource.register_diagram_vpc(current_vpc)
            peering_resources.append(new_peering_resource)

    for flow_logs in ec2.describe_flow_logs()['FlowLogs']:
        if flow_logs['ResourceId'] == current_vpc:
            flow_logs_resources.append(FlowLogsResource(flow_logs['FlowLogId'], name_from_tags(flow_logs)))

    existing_resource_endpoints = []
    for vpc_endpoint in ec2.describe_vpc_endpoints()['VpcEndpoints']:
        if in_vpc(vpc_endpoint):
            add_new = True
            for existing_service in existing_resource_endpoints:
                if existing_service.get_servicename() == vpc_endpoint['ServiceName']:
                    #if endpoint for service already exists, add vpce id to existing instead of creating new resource
                    existing_service.add_vpce_id(vpc_endpoint['VpcEndpointId'])
                    add_new = False
                    for rt in vpc_endpoint['RouteTableIds']:
                        existing_service.register_rt_association(rt)
                    break

            if add_new:
                new_endpoint_resource = VpcEndpointResource(vpc_endpoint['ServiceName'],
                                                            vpc_endpoint['VpcEndpointType'])

                new_endpoint_resource.add_vpce_id(vpc_endpoint['VpcEndpointId'])

                for rt in vpc_endpoint['RouteTableIds']:
                    new_endpoint_resource.register_rt_association(rt)

                existing_resource_endpoints.append(new_endpoint_resource)
                endpoints_resources.append(new_endpoint_resource)

    for vpn_gw in ec2.describe_vpn_gateways()['VpnGateways']:
        for attachment in vpn_gw['VpcAttachments']:
            if in_vpc(attachment):
                vpn = ""
                for conn in ec2.describe_vpn_connections()['VpnConnections']:
                    if conn['VpnGatewayId'] == vpn_gw['VpnGatewayId']:
                        vpn = conn['VpnConnectionId']
                vpn_gw_resources.append(VpnGatewayResource(vpn_gw['VpnGatewayId'], name_from_tags(vpn_gw), vpn))

    for dhcp_opts in ec2.describe_dhcp_options()['DhcpOptions']:
        if dhcp_opts_id == dhcp_opts['DhcpOptionsId']:
            for opt in dhcp_opts['DhcpConfigurations']:
                if opt['Key'] == 'domain-name-servers':
                    for val in opt['Values']:
                        dhcp_opt_dns_servers.append(val['Value'])
                elif opt['Key'] == 'domain-name':
                    for val in opt['Values']:
                        dhcp_opt_domains.append(val['Value'])

    for egress_gateway in ec2.describe_egress_only_internet_gateways()['EgressOnlyInternetGateways']:
        for attached in egress_gateway['Attachments']:
            if in_vpc(attached):
                egress_gateway_resources.append(IgwResource(egress_gateway['EgressOnlyInternetGatewayId'], current_vpc, name_from_tags(egress_gateway)))

    #create direct connect client for specialized boto3 request
    dc_client = SESSION.client('directconnect')
    for dc in dc_client.describe_direct_connect_gateways()['directConnectGateways']:
        id = dc['directConnectGatewayId']
        dc_association_list = dc_client.describe_direct_connect_gateway_associations(directConnectGatewayId=id)['directConnectGatewayAssociations']
        new_direct_connect_resource = DirectConnectResource(id, dc['directConnectGatewayName'])
        dc_associated = False
        for assoc in dc_association_list:
            for vg_dc in vpn_gw_resources:
                if assoc['virtualGatewayId'] == vg_dc.get_id():
                    dc_associated = True
                    new_direct_connect_resource.add_association(assoc['virtualGatewayId'])
        if dc_associated:
            direct_connect_resources.append(new_direct_connect_resource)

    current_vpc_resource = VpcResource(current_vpc, name, vpc_cidr)
    current_vpc_resource.add_dns_servers_from_opts(dhcp_opt_dns_servers)
    current_vpc_resource.add_domains_from_opts(dhcp_opt_domains)

    #add az resources to vpc
    for az in az_resources:
        current_vpc_resource.register_az(az)

    for assoc in nacl_association_data:
        for sub in subnet_resources:
            if assoc[0] == sub.get_id():
                sub.register_nacl_association(assoc)

    for rt in rt_resources:
        current_vpc_resource.register_rt(rt)

    #compute a column assignment for each nacl given total resources and number cols desired
    i = 0
    div = int(math.ceil(float(len(nacl_resources)) / SUBNET_ALIGNMENT_COLS))
    for nacl in nacl_resources:
        nacl.add_col_suggestion(int(i / div))
        current_vpc_resource.register_nacl(nacl)
        i+=1

    region = RegionResource(region)
    region.register_vpc(current_vpc_resource)

    #render diagram elements
    external_resource_space = (RESOURCE_DISTRIBUTION + (RESOURCE_DISTRIBUTION *
                                    (len(peering_resources) +
                                     len(igw_resources) +
                                     len(endpoints_resources) +
                                     len(vpn_gw_resources) +
                                     len(egress_gateway_resources))))

    account = AccountResource(profile)
    region_dimensions = region.get_dimensions(region_height_override=external_resource_space)
    region_bottom_y = region_dimensions[1] + VPC_GUTTER_DIM
    region_right_x = region_dimensions[0] + VPC_GUTTER_DIM
    account.set_dimensions(region_right_x + VPC_GUTTER_DIM + RESOURCE_DISTRIBUTION + PADDING,
                           region_bottom_y + PADDING)
    account.render_xml(xml_root, -PADDING,0)

    region.render_xml(xml_root, VPC_GUTTER_DIM, VPC_GUTTER_DIM, region_height_override=external_resource_space)

    #add resources not explicitly in the formatted region
    peering_x = VPC_GUTTER_DIM + int(PADDING / 2) + current_vpc_resource.get_dimensions()[0]
    peering_y = VPC_GUTTER_DIM + PADDING + RESOURCE_DISTRIBUTION
    peering_route_generator = RouteGroup(peering_x + (2 * RESOURCE_DISTRIBUTION) + PADDING, -1, X_DIRECTION)

    for conn in peering_resources:
        conn.render_xml(xml_root, peering_x, peering_y, peering_route_generator)
        peering_y += RESOURCE_DISTRIBUTION

    igw_x = peering_x
    igw_y = peering_y
    for igw in igw_resources:
        igw.render_xml(xml_root, igw_x, igw_y)
        igw_y += RESOURCE_DISTRIBUTION

    end_pt_route_generator = RouteGroup(VPC_GUTTER_DIM + int(PADDING / 2), -1, X_DIRECTION)
    ep_x = igw_x
    ep_y = igw_y
    for ep in endpoints_resources:
        ep.render_xml(xml_root, ep_x, ep_y, end_pt_route_generator)
        ep_y += RESOURCE_DISTRIBUTION

    vpn_x = ep_x
    vpn_y = ep_y
    for vpn in vpn_gw_resources:
        vpn.render_xml(xml_root, vpn_x, vpn_y)
        vpn_y += RESOURCE_DISTRIBUTION

    egress_gw_x = peering_x
    egress_gw_y = vpn_y
    for egw in egress_gateway_resources:
        egw.render_xml(xml_root, egress_gw_x, egress_gw_y)
        egress_gw_y += RESOURCE_DISTRIBUTION

    original_peer_vpc_spacing = peering_x + VPC_GUTTER_DIM
    if ADD_ROUTE_TABLE_CONNECTIONS:
        original_peer_vpc_spacing += VPC_GUTTER_DIM

    peer_vpc_x = original_peer_vpc_spacing
    peer_vpc_y = VPC_GUTTER_DIM + PADDING + RESOURCE_DISTRIBUTION - 20
    peer_empty_dim = (0, 0)
    if peer_vpc_resources:
        peer_empty_dim = peer_vpc_resources[0].get_dimensions()

    count_right = 0
    for peer_vpc in peer_vpc_resources:
        if count_right == VPC_PEER_COLS:
            peer_vpc_x = original_peer_vpc_spacing
            peer_vpc_y += peer_empty_dim[1] + PADDING
            count_right = 0
        peer_vpc.render_xml(xml_root, peer_vpc_x, peer_vpc_y)
        peer_vpc_x += peer_empty_dim[0] + PADDING
        count_right += 1

    fl_x = VPC_GUTTER_DIM + RESOURCE_DISTRIBUTION + PADDING
    fl_y = VPC_GUTTER_DIM + PADDING - 30
    for fl in flow_logs_resources:
        fl.render_xml(xml_root, fl_x, fl_y)
        fl_x += RESOURCE_DISTRIBUTION

    dc_x = original_peer_vpc_spacing
    dc_y = vpn_y - RESOURCE_DISTRIBUTION
    for dc in direct_connect_resources:
        dc.render_xml(xml_root, dc_x, dc_y)
        dc_y += RESOURCE_DISTRIBUTION

    #create xml and write to file
    xml_diagram_tree = ET.ElementTree(xml_doc)
    filename = "{}.xml".format(current_vpc)
    save_path = "{}{}".format(make_save_location(dir), filename)
    xml_diagram_tree.write(save_path)
    return save_path

def main(profile, region, vpc_name, save_directory):

    vpc_exists = False
    ec2 = SESSION.client('ec2')

    available_vpcs = []
    for vpc in ec2.describe_vpcs()['Vpcs']:
        available_vpcs.append(vpc['VpcId'])
        if vpc['VpcId'] == vpc_name:
            vpc_exists = True
            cidr = vpc['CidrBlock']
            name = name_from_tags(vpc)
            dhcp_opts = vpc['DhcpOptionsId']
            break

    if vpc_exists:
        doc = create_xml_doc()
        filename = visualize_vpc(ec2, region, vpc_name, name, cidr, dhcp_opts, save_directory, profile, doc)
        print("Wrote diagram to {}".format(filename))
        return 0

    else:
        print("\nVpc: {} not found\n".format(vpc_name))
        print("The following vpcs exist in profile: {}, region: {}:\n".format(profile, region))

        #list vpcs available
        for existing_vpc in available_vpcs:
            print("->\t {}".format(existing_vpc))
        print("")

        exit(1)

def lambda_handler(json_input, context):
    """aws lambda-specific execution procedure"""

    ec2 = SESSION.client('ec2')
    region = SESSION.region_name
    s3_client = SESSION.client('s3')

    #retrieve environment variables
    bucket = os.environ['OUTPUT_BUCKET']
    account_name = os.environ['ACCOUNT_NAME']

    for vpc in ec2.describe_vpcs()['Vpcs']:
        vpc_id = vpc['VpcId']
        cidr = vpc['CidrBlock']
        name = name_from_tags(vpc)
        dhcp_opts = vpc['DhcpOptionsId']
        new_doc = create_xml_doc()
        filename = visualize_vpc(ec2,region,vpc_id,name,cidr,dhcp_opts,"/tmp",account_name,new_doc)

        print("LOG Wrote diagram to {}".format(filename))

        #upload file to s3
        with open(filename) as upload_file:
            output_filename = "{}.xml".format(vpc_id)

            print("LOG Writing {} to s3://{}/{}".format(filename, bucket, output_filename))

            object = upload_file.read()
            s3_client.put_object(Body=object,
                                 Bucket=bucket,
                                 Key=output_filename,
                                 ContentType='application/xml')

if __name__ == "__main__":
    main(args.profile, args.region, args.vpc, args.directory)
